from __future__ import annotations

from faculties import FACULTIES
from live_fetch import extract_candidate_links, fetch_page
from page_index import detect_faculty_id, detect_page_type, save_index

PRIORITY_PATHS = [
    "/orare/",
    "/orar/",
    "/studenti/",
    "/contact/",
    "/admitere/",
    "/burse/",
    "/secretariat/",
]
MAX_LINKS_PER_SEED = 30


def unique_urls(urls: list[str]) -> list[str]:
    seen = set()
    unique = []

    for url in urls:
        if not url or url in seen:
            continue

        seen.add(url)
        unique.append(url)

    return unique


def build_seed_urls(base_urls: list[str]) -> list[str]:
    candidates = []

    for base_url in base_urls:
        candidates.append(base_url)

        for path in PRIORITY_PATHS:
            candidates.append(base_url.rstrip("/") + path)

    return unique_urls(candidates)


def build_index() -> list[dict]:
    items = []
    seen_urls = set()

    for faculty in FACULTIES:
        base_urls = faculty["base_urls"]
        candidates = build_seed_urls(base_urls)

        for seed_url in list(candidates):
            candidates.extend(extract_candidate_links(seed_url, base_urls, max_links=MAX_LINKS_PER_SEED))

        for url in unique_urls(candidates):
            if url in seen_urls:
                continue

            seen_urls.add(url)
            page = fetch_page(url)
            if not page.get("text"):
                continue

            items.append({
                "faculty_id": detect_faculty_id(page["url"], FACULTIES),
                "url": page["url"],
                "title": page.get("title", page["url"]),
                "text": page.get("text", "")[:5000],
                "page_type": detect_page_type(
                    page["url"],
                    page.get("title", ""),
                    page.get("text", ""),
                ),
            })

    save_index(items)
    return items


if __name__ == "__main__":
    built_items = build_index()
    print(f"Indexed {len(built_items)} pages")
