from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from faculties import FACULTIES
from live_fetch import clear_fetch_caches, extract_candidate_links, fetch_page, get_url_extension
from page_index import (
    bound_index_text,
    build_index_document,
    normalize_index_document,
    normalize_url,
    page_text_limits,
    save_index,
)
from vector_indexer import rebuild_vector_index

PRIORITY_PATHS = (
    "/orare/",
    "/orar/",
    "/burse/",
    "/contact/",
    "/secretariat/",
    "/studenti/",
    "/admitere/",
    "/regulamente/",
    "/regulament/",
    "/metodologii/",
    "/metodologie/",
    "/proceduri/",
    "/procedura/",
)

HTML_EXTENSIONS = {"", ".html", ".htm", ".php", ".aspx"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SITEMAP_PATHS = ("sitemap.xml", "wp-sitemap.xml")
SITEMAP_TIMEOUT = 12
SITEMAP_MAX_DEPTH = 4


def unique_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for url in urls:
        normalized = normalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(url)

    return ordered


def is_html_like_url(url: str) -> bool:
    return get_url_extension(url) in HTML_EXTENSIONS


def normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip()
    return host[4:] if host.startswith("www.") else host


def same_allowed_domain(url: str, base_urls: list[str]) -> bool:
    host = normalize_host(url)
    return bool(host) and any(host == normalize_host(base_url) for base_url in base_urls)


def is_indexable_url(url: str, base_urls: list[str]) -> bool:
    if not same_allowed_domain(url, base_urls):
        return False
    extension = get_url_extension(url)
    return extension in HTML_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS


def sitemap_seed_urls(base_urls: list[str]) -> list[str]:
    seeds: list[str] = []
    for base_url in base_urls:
        for path in SITEMAP_PATHS:
            seeds.append(urljoin(base_url, path))
    return unique_urls(seeds)


def fetch_sitemap_locations(sitemap_url: str) -> list[str]:
    try:
        response = requests.get(sitemap_url, timeout=(3, SITEMAP_TIMEOUT), headers={"User-Agent": "UVT_Asist/1.0"})
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    return [node.get_text(strip=True) for node in soup.find_all("loc") if node.get_text(strip=True)]


def has_url_capacity(current_count: int, max_urls: int) -> bool:
    return max_urls <= 0 or current_count < max_urls


def discover_sitemap_urls(base_urls: list[str], max_urls: int) -> list[str]:
    queue = deque((url, 0) for url in sitemap_seed_urls(base_urls))
    seen_sitemaps: set[str] = set()
    discovered: list[str] = []
    seen_urls: set[str] = set()

    while queue and has_url_capacity(len(discovered), max_urls):
        sitemap_url, depth = queue.popleft()
        normalized_sitemap = normalize_url(sitemap_url)
        if not normalized_sitemap or normalized_sitemap in seen_sitemaps or depth > SITEMAP_MAX_DEPTH:
            continue
        seen_sitemaps.add(normalized_sitemap)

        for location in fetch_sitemap_locations(sitemap_url):
            normalized_location = normalize_url(location)
            if not normalized_location:
                continue

            extension = get_url_extension(location)
            if extension == ".xml" and "sitemap" in normalized_location and depth < SITEMAP_MAX_DEPTH:
                queue.append((location, depth + 1))
                continue

            if not is_indexable_url(location, base_urls) or normalized_location in seen_urls:
                continue

            seen_urls.add(normalized_location)
            discovered.append(location)
            if not has_url_capacity(len(discovered), max_urls):
                break

    return discovered


def build_seed_urls(base_urls: list[str], use_sitemaps: bool = True, max_sitemap_urls: int = 250) -> list[str]:
    seeds: list[str] = []
    for base_url in base_urls:
        seeds.append(base_url)
        seeds.extend(urljoin(base_url, path.lstrip("/")) for path in PRIORITY_PATHS)
    if use_sitemaps:
        seeds.extend(discover_sitemap_urls(base_urls, max_urls=max_sitemap_urls))
    return unique_urls(seeds)


def score_url(url: str) -> tuple[int, int, str]:
    normalized = normalize_url(url)
    extension = get_url_extension(normalized)
    score = 0

    for path in PRIORITY_PATHS:
        if path.rstrip("/") in normalized:
            score += 30

    if extension in DOCUMENT_EXTENSIONS:
        score += 14
    elif extension in IMAGE_EXTENSIONS:
        score += 8
    elif extension in HTML_EXTENSIONS:
        score += 10

    depth_penalty = normalized.count("/")
    return score, -depth_penalty, normalized


def sort_urls(urls: list[str]) -> list[str]:
    return sorted(unique_urls(urls), key=score_url, reverse=True)


def discover_faculty_urls(
    faculty: dict,
    max_urls: int,
    max_depth: int,
    max_links_per_page: int,
    use_sitemaps: bool = True,
) -> list[str]:
    base_urls = faculty.get("base_urls", [])
    seeds = sort_urls(build_seed_urls(base_urls, use_sitemaps=use_sitemaps, max_sitemap_urls=max_urls))
    queue = deque((url, 0) for url in seeds if is_html_like_url(url))
    seen = {normalize_url(url) for url in seeds}
    results = list(seeds)

    while queue and has_url_capacity(len(results), max_urls):
        current_url, depth = queue.popleft()
        if depth >= max_depth:
            continue

        discovered_links = sort_urls(
            extract_candidate_links(current_url, base_urls, max_links=max_links_per_page)
        )
        for discovered_url in discovered_links:
            normalized = normalize_url(discovered_url)
            if not normalized or normalized in seen:
                continue

            seen.add(normalized)
            results.append(discovered_url)
            if is_html_like_url(discovered_url):
                queue.append((discovered_url, depth + 1))
            if not has_url_capacity(len(results), max_urls):
                break

    return sort_urls(results)


def fetch_pages(urls: list[str], max_workers: int) -> list[dict]:
    selected_urls = unique_urls(urls)
    if not selected_urls:
        return []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(selected_urls))) as executor:
        pages = list(executor.map(safe_fetch_page, selected_urls))

    return [page for page in pages if page.get("text")]


def compact_page_for_index(page: dict) -> dict:
    url = str(page.get("url") or "").strip()
    max_text_chars, _ = page_text_limits(url)
    return {
        "url": url,
        "title": bound_index_text(page.get("title"), 500).strip(),
        "text": bound_index_text(page.get("text"), max_text_chars).strip(),
        "type": str(page.get("type") or "unknown").strip(),
        "faculty_id": page.get("faculty_id"),
        "page_type": page.get("page_type"),
    }


def describe_exception(exc: Exception) -> str:
    message = str(exc).strip()
    exception_type = type(exc).__name__
    return f"{exception_type}: {message}" if message else exception_type


def safe_fetch_page(url: str) -> dict:
    try:
        return fetch_page(url, index_mode=True)
    except Exception as exc:
        return {
            "url": url,
            "title": url,
            "text": "",
            "error": describe_exception(exc),
            "type": "error",
        }


def fetch_pages_with_errors(urls: list[str], max_workers: int) -> list[dict]:
    selected_urls = unique_urls(urls)
    if not selected_urls:
        return []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(selected_urls))) as executor:
        return list(executor.map(safe_fetch_page, selected_urls))


def emit_progress(callback: Callable[[dict], None] | None, event: str, **data) -> None:
    if callback:
        callback({"event": event, **data})


def build_index(
    max_urls_per_faculty: int = 90,
    max_depth: int = 2,
    max_links_per_page: int = 35,
    fetch_workers: int = 10,
    use_sitemaps: bool = True,
    skip_vector_index: bool = False,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    seen_urls: set[str] = set()
    pages: list[dict] = []
    index_errors: list[dict] = []
    total_faculties = len(FACULTIES)

    emit_progress(
        progress,
        "started",
        phase="discovering",
        progress=1,
        processed_faculties=0,
        total_faculties=total_faculties,
        discovered_urls=0,
        fetched_pages=0,
        error_count=0,
    )

    for index, faculty in enumerate(FACULTIES, start=1):
        faculty_id = faculty.get("id", "uvt")
        faculty_name = faculty.get("name", faculty.get("id", "UVT"))
        faculty_start_progress = 3 + int(((index - 1) / max(total_faculties, 1)) * 68)
        emit_progress(
            progress,
            "faculty_start",
            phase="discovering",
            progress=faculty_start_progress,
            current_faculty=faculty_name,
            processed_faculties=index - 1,
            total_faculties=total_faculties,
            discovered_urls=len(seen_urls),
            fetched_pages=len(pages),
            error_count=len(index_errors),
        )
        try:
            candidate_urls = discover_faculty_urls(
                faculty,
                max_urls=max_urls_per_faculty,
                max_depth=max_depth,
                max_links_per_page=max_links_per_page,
                use_sitemaps=use_sitemaps,
            )
        except Exception as exc:
            index_errors.append({
                "faculty_id": faculty_id,
                "faculty_name": faculty_name,
                "stage": "discover",
                "error": describe_exception(exc),
            })
            emit_progress(
                progress,
                "faculty_error",
                phase="discovering",
                progress=faculty_start_progress,
                current_faculty=faculty_name,
                processed_faculties=index,
                total_faculties=total_faculties,
                discovered_urls=len(seen_urls),
                fetched_pages=len(pages),
                error_count=len(index_errors),
            )
            clear_fetch_caches()
            continue

        emit_progress(
            progress,
            "faculty_discovered",
            phase="fetching",
            progress=min(74, faculty_start_progress + 2),
            current_faculty=faculty_name,
            processed_faculties=index - 1,
            total_faculties=total_faculties,
            discovered_urls=len(seen_urls) + len(candidate_urls),
            faculty_urls=len(candidate_urls),
            fetched_pages=len(pages),
            error_count=len(index_errors),
        )
        faculty_urls: list[str] = []
        for url in candidate_urls:
            normalized = normalize_url(url)
            if normalized and normalized not in seen_urls:
                seen_urls.add(normalized)
                faculty_urls.append(url)

        try:
            fetched_faculty_pages = fetch_pages_with_errors(faculty_urls, fetch_workers)
        except Exception as exc:
            index_errors.append({
                "faculty_id": faculty_id,
                "faculty_name": faculty_name,
                "stage": "fetch",
                "error": describe_exception(exc),
            })
            fetched_faculty_pages = []

        faculty_errors = [page for page in fetched_faculty_pages if page.get("error")]
        for page in faculty_errors:
            index_errors.append({
                "faculty_id": faculty_id,
                "faculty_name": faculty_name,
                "stage": "fetch",
                "url": page.get("url", ""),
                "error": page.get("error", "Fetch failed."),
            })

        faculty_pages = [
            compact_page_for_index(page)
            for page in fetched_faculty_pages
            if page.get("text")
        ]
        pages.extend(faculty_pages)
        clear_fetch_caches()
        emit_progress(
            progress,
            "faculty_fetched",
            phase="fetching",
            progress=min(78, 3 + int((index / max(total_faculties, 1)) * 72)),
            current_faculty=faculty_name,
            processed_faculties=index,
            total_faculties=total_faculties,
            discovered_urls=len(seen_urls),
            fetched_pages=len(pages),
            faculty_pages=len(faculty_pages),
            faculty_errors=len(faculty_errors),
            error_count=len(index_errors),
        )

    index_document = build_index_document(pages, FACULTIES)
    if index_errors:
        index_document["index_error_count"] = len(index_errors)
        index_document["index_errors"] = index_errors[:100]
    index_document = normalize_index_document(index_document)
    emit_progress(
        progress,
        "json_built",
        phase="chunking",
        progress=80,
        page_count=index_document.get("page_count", 0),
        chunk_count=index_document.get("chunk_count", 0),
        fetched_pages=len(pages),
        discovered_urls=len(seen_urls),
        error_count=len(index_errors),
    )

    if not skip_vector_index:
        chunk_count = max(1, int(index_document.get("chunk_count", 0) or 0))
        emit_progress(
            progress,
            "vector_start",
            phase="embedding",
            progress=82,
            page_count=index_document.get("page_count", 0),
            chunk_count=index_document.get("chunk_count", 0),
            error_count=len(index_errors),
        )

        def vector_progress(done: int, total: int) -> None:
            total = max(total, chunk_count)
            emit_progress(
                progress,
                "vector_progress",
                phase="embedding",
                progress=min(98, 82 + int((done / max(total, 1)) * 16)),
                embedded_chunks=done,
                total_chunks=total,
                page_count=index_document.get("page_count", 0),
                chunk_count=index_document.get("chunk_count", 0),
                error_count=len(index_errors),
            )

        vector_status = rebuild_vector_index(index_document, recreate=True, progress=vector_progress)
        index_document["vector_index"] = vector_status
        emit_progress(
            progress,
            "vector_done",
            phase="saving",
            progress=99,
            page_count=index_document.get("page_count", 0),
            chunk_count=index_document.get("chunk_count", 0),
            vector_indexed_count=vector_status.get("indexed_count", 0),
            error_count=len(index_errors),
        )

    save_index(index_document)
    emit_progress(
        progress,
        "saved",
        phase="ready",
        progress=100,
        page_count=index_document.get("page_count", 0),
        chunk_count=index_document.get("chunk_count", 0),
        discovered_urls=len(seen_urls),
        fetched_pages=len(pages),
        error_count=len(index_errors),
    )
    return index_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local UVT RAG index.")
    parser.add_argument("--max-urls-per-faculty", type=int, default=90, help="Use 0 for no per-faculty URL cap.")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-links-per-page", type=int, default=35)
    parser.add_argument("--fetch-workers", type=int, default=10)
    parser.add_argument(
        "--no-sitemaps",
        action="store_true",
        help="Disable sitemap discovery and use only priority paths plus link crawling.",
    )
    parser.add_argument(
        "--full-site",
        action="store_true",
        help="Use a broader crawl preset for a more complete local runtime snapshot.",
    )
    parser.add_argument(
        "--skip-vector-index",
        action="store_true",
        help="Only rebuild backend/data/page_index.json. Normal thesis runs should leave this off.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    max_urls_per_faculty = args.max_urls_per_faculty
    max_depth = args.max_depth
    max_links_per_page = args.max_links_per_page
    fetch_workers = args.fetch_workers

    if args.full_site:
        max_urls_per_faculty = 0 if max_urls_per_faculty == 90 else max_urls_per_faculty
        max_depth = max(max_depth, 4)
        max_links_per_page = max(max_links_per_page, 100)
        fetch_workers = max(fetch_workers, 12)

    document = build_index(
        max_urls_per_faculty=max_urls_per_faculty if max_urls_per_faculty <= 0 else max(20, max_urls_per_faculty),
        max_depth=max(0, max_depth),
        max_links_per_page=max(10, max_links_per_page),
        fetch_workers=max(1, fetch_workers),
        use_sitemaps=not args.no_sitemaps,
        skip_vector_index=args.skip_vector_index,
    )
    print(
        f"Indexed {document['page_count']} pages into {document['chunk_count']} chunks "
        f"(schema v{document['schema_version']})"
    )
    if document.get("vector_index"):
        vector_index = document["vector_index"]
        vector_location = vector_index.get("qdrant_path") or vector_index.get("qdrant_url")
        print(
            f"Vector index: {vector_index['indexed_count']} chunks in Qdrant collection "
            f"{vector_index['collection']} at {vector_location} using {vector_index['embedding_model']} "
            f"({vector_index['vector_size']} dimensions)"
        )
