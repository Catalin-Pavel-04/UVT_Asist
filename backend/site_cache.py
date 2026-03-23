from __future__ import annotations

import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
from faculties import FACULTIES
from live_fetch import extract_candidate_links, fetch_page, get_url_extension
from retriever import build_page_chunks

ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}
PRIORITY_PATHS = (
    "/orare/",
    "/orar/",
    "/studenti/",
    "/contact/",
    "/admitere/",
    "/burse/",
    "/secretariat/",
)
HTML_LIKE_EXTENSIONS = ("", ".html", ".htm", ".php", ".aspx")
DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".txt")
OCR_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

CACHE_REFRESH_SECONDS = max(60, int(os.getenv("CACHE_REFRESH_SECONDS", "10800")))
CACHE_DISCOVERY_LINKS = max(1, int(os.getenv("CACHE_DISCOVERY_LINKS", "30")))
CACHE_MAX_URLS_PER_FACULTY = max(10, int(os.getenv("CACHE_MAX_URLS_PER_FACULTY", "120")))
CACHE_MAX_HTML_PAGES_PER_FACULTY = max(5, int(os.getenv("CACHE_MAX_HTML_PAGES_PER_FACULTY", "50")))
CACHE_MAX_CRAWL_DEPTH = max(0, int(os.getenv("CACHE_MAX_CRAWL_DEPTH", "3")))
CACHE_PAGE_FETCH_WORKERS = max(1, int(os.getenv("CACHE_PAGE_FETCH_WORKERS", "8")))
CACHE_FACULTY_REFRESH_WORKERS = max(1, int(os.getenv("CACHE_FACULTY_REFRESH_WORKERS", "4")))

STATE_LOCK = threading.Lock()
START_LOCK = threading.Lock()
REFRESH_STARTED = False

CACHE_STATE = {
    "faculties": {},
    "refresh_in_progress": False,
    "last_refresh_started_at": None,
    "last_refresh_completed_at": None,
    "last_error": "",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_hostname(hostname: str) -> str:
    hostname = hostname.strip().lower()
    if hostname.startswith("www."):
        return hostname[4:]

    return hostname


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    host = _normalize_hostname(parsed.hostname or "")
    path = parsed.path.rstrip("/") or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{host}{path}{query}"


def _unique_urls(urls: list[str]) -> list[str]:
    seen = set()
    unique = []

    for url in urls:
        normalized_url = _normalize_url(url)
        if normalized_url in seen:
            continue

        unique.append(url)
        seen.add(normalized_url)

    return unique


def _is_html_like_url(url: str) -> bool:
    return get_url_extension(url) in HTML_LIKE_EXTENSIONS


def _score_discovered_url(url: str) -> tuple[int, int]:
    normalized_url = url.lower()
    extension = get_url_extension(normalized_url)
    score = 0

    if any(path in normalized_url for path in PRIORITY_PATHS):
        score += 30

    if extension in DOCUMENT_EXTENSIONS:
        score += 12
    elif extension in OCR_IMAGE_EXTENSIONS:
        score += 8
    elif _is_html_like_url(url):
        score += 10

    path_length = len(normalized_url)
    return (score, -path_length)


def _sort_discovered_urls(urls: list[str]) -> list[str]:
    return sorted(_unique_urls(urls), key=_score_discovered_url, reverse=True)


def _fetch_pages(urls: list[str]) -> list[dict]:
    selected_urls = _unique_urls(urls)
    if not selected_urls:
        return []

    with ThreadPoolExecutor(max_workers=min(CACHE_PAGE_FETCH_WORKERS, len(selected_urls))) as executor:
        pages = list(executor.map(fetch_page, selected_urls))

    return [page for page in pages if page.get("text")]


def _build_seed_urls(faculty_id: str) -> list[str]:
    faculty = FACULTY_MAP[faculty_id]
    base_urls = faculty["base_urls"]
    candidates = []

    for base_url in base_urls:
        candidates.append(base_url)

        for path in PRIORITY_PATHS:
            candidates.append(urljoin(base_url, path.lstrip("/")))

    return _unique_urls(candidates)


def _build_faculty_urls(faculty_id: str) -> list[str]:
    faculty = FACULTY_MAP[faculty_id]
    base_urls = faculty["base_urls"]
    seed_urls = _build_seed_urls(faculty_id)
    results = list(seed_urls)
    seen = {_normalize_url(url) for url in seed_urls}
    queue = deque((url, 0) for url in seed_urls if _is_html_like_url(url))
    html_pages_explored = 0

    while queue and len(results) < CACHE_MAX_URLS_PER_FACULTY and html_pages_explored < CACHE_MAX_HTML_PAGES_PER_FACULTY:
        current_url, depth = queue.popleft()
        html_pages_explored += 1

        if depth >= CACHE_MAX_CRAWL_DEPTH:
            continue

        discovered_urls = _sort_discovered_urls(
            extract_candidate_links(current_url, base_urls, max_links=CACHE_DISCOVERY_LINKS)
        )

        for discovered_url in discovered_urls:
            normalized_url = _normalize_url(discovered_url)
            if normalized_url in seen:
                continue

            seen.add(normalized_url)
            results.append(discovered_url)

            if _is_html_like_url(discovered_url):
                queue.append((discovered_url, depth + 1))

            if len(results) >= CACHE_MAX_URLS_PER_FACULTY:
                break

    return _unique_urls(results)


def refresh_faculty_cache(faculty_id: str) -> dict:
    urls = _build_faculty_urls(faculty_id)
    pages = _fetch_pages(urls)
    chunks = build_page_chunks(pages)

    faculty_cache = {
        "pages": pages,
        "chunks": chunks,
        "page_count": len(pages),
        "chunk_count": len(chunks),
        "last_refresh_at": _utc_now_iso(),
    }

    with STATE_LOCK:
        CACHE_STATE["faculties"][faculty_id] = faculty_cache

    return faculty_cache


def refresh_all_faculties() -> None:
    with STATE_LOCK:
        CACHE_STATE["refresh_in_progress"] = True
        CACHE_STATE["last_refresh_started_at"] = _utc_now_iso()
        CACHE_STATE["last_error"] = ""

    errors = []

    with ThreadPoolExecutor(max_workers=min(CACHE_FACULTY_REFRESH_WORKERS, len(FACULTIES))) as executor:
        future_map = {
            executor.submit(refresh_faculty_cache, faculty["id"]): faculty["id"]
            for faculty in FACULTIES
        }

        for future in as_completed(future_map):
            faculty_id = future_map[future]
            try:
                future.result()
            except Exception as exc:
                errors.append(f"{faculty_id}: {exc}")

    with STATE_LOCK:
        CACHE_STATE["refresh_in_progress"] = False
        CACHE_STATE["last_refresh_completed_at"] = _utc_now_iso()
        CACHE_STATE["last_error"] = " | ".join(errors[:3])


def _record_refresh_failure(exc: Exception) -> None:
    with STATE_LOCK:
        CACHE_STATE["refresh_in_progress"] = False
        CACHE_STATE["last_refresh_completed_at"] = _utc_now_iso()
        CACHE_STATE["last_error"] = str(exc)


def _refresh_loop() -> None:
    while True:
        try:
            refresh_all_faculties()
        except Exception as exc:
            _record_refresh_failure(exc)

        time.sleep(CACHE_REFRESH_SECONDS)


def ensure_background_refresh_started() -> None:
    global REFRESH_STARTED

    with START_LOCK:
        if REFRESH_STARTED:
            return

        thread = threading.Thread(target=_refresh_loop, daemon=True, name="uvt-site-cache-refresh")
        thread.start()
        REFRESH_STARTED = True


def get_cached_pages(faculty_id: str) -> list[dict]:
    with STATE_LOCK:
        faculty_cache = CACHE_STATE["faculties"].get(faculty_id) or {}
        return list(faculty_cache.get("pages", []))


def get_cached_chunks(faculty_id: str) -> list[dict]:
    with STATE_LOCK:
        faculty_cache = CACHE_STATE["faculties"].get(faculty_id) or {}
        return list(faculty_cache.get("chunks", []))


def get_cache_status() -> dict:
    with STATE_LOCK:
        faculty_state = CACHE_STATE["faculties"]
        return {
            "started": REFRESH_STARTED,
            "refresh_in_progress": CACHE_STATE["refresh_in_progress"],
            "last_refresh_started_at": CACHE_STATE["last_refresh_started_at"],
            "last_refresh_completed_at": CACHE_STATE["last_refresh_completed_at"],
            "last_error": CACHE_STATE["last_error"],
            "ready_faculties": len(faculty_state),
            "faculty_pages": {
                faculty_id: data.get("page_count", 0)
                for faculty_id, data in faculty_state.items()
            },
            "crawl_limits": {
                "refresh_seconds": CACHE_REFRESH_SECONDS,
                "discovery_links": CACHE_DISCOVERY_LINKS,
                "max_urls_per_faculty": CACHE_MAX_URLS_PER_FACULTY,
                "max_html_pages_per_faculty": CACHE_MAX_HTML_PAGES_PER_FACULTY,
                "max_crawl_depth": CACHE_MAX_CRAWL_DEPTH,
            },
        }
