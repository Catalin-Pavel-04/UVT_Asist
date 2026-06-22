from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from core.config import env_int
from live_fetch import fetch_page

VERIFICATION_CACHE_TTL = env_int("VERIFICATION_CACHE_TTL", "1800", minimum=60)
VERIFICATION_FETCH_WORKERS = env_int("VERIFICATION_FETCH_WORKERS", "3", minimum=1)

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


def verification_cache_key(url: str, index_mode: bool = False) -> str:
    return f"{url}|index={int(index_mode)}"


def get_cached_page(cache_key: str, now: float) -> dict | None:
    with STATE_LOCK:
        cached = VERIFICATION_CACHE.get(cache_key)
        if cached and now - cached["timestamp"] < VERIFICATION_CACHE_TTL:
            return {
                **cached["page"],
                "cache_hit": True,
                "verified_at": cached["verified_at"],
            }
    return None


def store_cached_page(cache_key: str, page: dict) -> dict:
    verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cached_page = {**page, "cache_hit": False, "verified_at": verified_at}

    with STATE_LOCK:
        VERIFICATION_CACHE[cache_key] = {
            "timestamp": time.time(),
            "verified_at": verified_at,
            "page": page,
        }

    return cached_page


def verify_pages(urls: list[str], max_pages: int = 2, index_mode: bool = False) -> list[dict]:
    selected_urls = unique_urls(urls)[:max_pages]
    if not selected_urls:
        return []

    now = time.time()
    results: dict[str, dict] = {}
    missing_urls: list[str] = []

    for url in selected_urls:
        cached_page = get_cached_page(verification_cache_key(url, index_mode), now)
        if cached_page:
            results[url] = cached_page
        else:
            missing_urls.append(url)

    if missing_urls:
        with ThreadPoolExecutor(max_workers=min(VERIFICATION_FETCH_WORKERS, len(missing_urls))) as executor:
            pages = list(executor.map(lambda item: fetch_page(item, index_mode=index_mode), missing_urls))

        for url, page in zip(missing_urls, pages):
            if page.get("text"):
                results[url] = store_cached_page(verification_cache_key(url, index_mode), page)

    return [results[url] for url in selected_urls if url in results]


def get_cache_status() -> dict:
    now = time.time()
    with STATE_LOCK:
        alive_entries = sum(1 for item in VERIFICATION_CACHE.values() if now - item["timestamp"] < VERIFICATION_CACHE_TTL)

    return {
        "ttl_seconds": VERIFICATION_CACHE_TTL,
        "entries": alive_entries,
    }
