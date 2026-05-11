from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from live_fetch import fetch_page

VERIFICATION_CACHE_TTL = max(60, int(os.getenv("VERIFICATION_CACHE_TTL", "1800")))
VERIFICATION_FETCH_WORKERS = max(1, int(os.getenv("VERIFICATION_FETCH_WORKERS", "3")))

STATE_LOCK = threading.Lock()
VERIFICATION_CACHE: dict[str, dict] = {}


def unique_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def get_cached_page(url: str, now: float) -> dict | None:
    with STATE_LOCK:
        cached = VERIFICATION_CACHE.get(url)
        if cached and now - cached["timestamp"] < VERIFICATION_CACHE_TTL:
            return {
                **cached["page"],
                "cache_hit": True,
                "verified_at": cached["verified_at"],
            }
    return None


def store_cached_page(url: str, page: dict) -> dict:
    verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cached_page = {**page, "cache_hit": False, "verified_at": verified_at}

    with STATE_LOCK:
        VERIFICATION_CACHE[url] = {
            "timestamp": time.time(),
            "verified_at": verified_at,
            "page": page,
        }

    return cached_page


def verify_pages(urls: list[str], max_pages: int = 2) -> list[dict]:
    selected_urls = unique_urls(urls)[:max_pages]
    if not selected_urls:
        return []

    now = time.time()
    results: dict[str, dict] = {}
    missing_urls: list[str] = []

    for url in selected_urls:
        cached_page = get_cached_page(url, now)
        if cached_page:
            results[url] = cached_page
        else:
            missing_urls.append(url)

    if missing_urls:
        with ThreadPoolExecutor(max_workers=min(VERIFICATION_FETCH_WORKERS, len(missing_urls))) as executor:
            pages = list(executor.map(fetch_page, missing_urls))

        for url, page in zip(missing_urls, pages):
            if page.get("text"):
                results[url] = store_cached_page(url, page)

    return [results[url] for url in selected_urls if url in results]


def get_cache_status() -> dict:
    now = time.time()
    with STATE_LOCK:
        alive_entries = sum(1 for item in VERIFICATION_CACHE.values() if now - item["timestamp"] < VERIFICATION_CACHE_TTL)

    return {
        "ttl_seconds": VERIFICATION_CACHE_TTL,
        "entries": alive_entries,
    }
