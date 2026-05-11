from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from faculties import FACULTIES
from live_fetch import extract_candidate_links, fetch_page, get_url_extension
from page_index import build_index_document, normalize_url, save_index
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


def build_seed_urls(base_urls: list[str]) -> list[str]:
    seeds: list[str] = []
    for base_url in base_urls:
        seeds.append(base_url)
        seeds.extend(urljoin(base_url, path.lstrip("/")) for path in PRIORITY_PATHS)
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
) -> list[str]:
    base_urls = faculty.get("base_urls", [])
    seeds = sort_urls(build_seed_urls(base_urls))
    queue = deque((url, 0) for url in seeds if is_html_like_url(url))
    seen = {normalize_url(url) for url in seeds}
    results = list(seeds)

    while queue and len(results) < max_urls:
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
            if len(results) >= max_urls:
                break

    return sort_urls(results)


def fetch_pages(urls: list[str], max_workers: int) -> list[dict]:
    selected_urls = unique_urls(urls)
    if not selected_urls:
        return []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(selected_urls))) as executor:
        pages = list(executor.map(fetch_page, selected_urls))

    return [page for page in pages if page.get("text")]


def build_index(
    max_urls_per_faculty: int = 90,
    max_depth: int = 2,
    max_links_per_page: int = 35,
    fetch_workers: int = 10,
    skip_vector_index: bool = False,
) -> dict:
    seen_urls: set[str] = set()
    pages: list[dict] = []

    for faculty in FACULTIES:
        candidate_urls = discover_faculty_urls(
            faculty,
            max_urls=max_urls_per_faculty,
            max_depth=max_depth,
            max_links_per_page=max_links_per_page,
        )
        faculty_urls: list[str] = []
        for url in candidate_urls:
            normalized = normalize_url(url)
            if normalized and normalized not in seen_urls:
                seen_urls.add(normalized)
                faculty_urls.append(url)

        pages.extend(fetch_pages(faculty_urls, fetch_workers))

    index_document = build_index_document(pages, FACULTIES)
    save_index(index_document)

    if not skip_vector_index:
        vector_status = rebuild_vector_index(index_document, recreate=True)
        index_document["vector_index"] = vector_status

    return index_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local UVT RAG index.")
    parser.add_argument("--max-urls-per-faculty", type=int, default=90)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-links-per-page", type=int, default=35)
    parser.add_argument("--fetch-workers", type=int, default=10)
    parser.add_argument(
        "--skip-vector-index",
        action="store_true",
        help="Only rebuild backend/data/page_index.json. Normal thesis runs should leave this off.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    document = build_index(
        max_urls_per_faculty=max(20, args.max_urls_per_faculty),
        max_depth=max(0, args.max_depth),
        max_links_per_page=max(10, args.max_links_per_page),
        fetch_workers=max(1, args.fetch_workers),
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
