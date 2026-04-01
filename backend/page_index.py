from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

INDEX_PATH = Path(__file__).with_name("data") / "page_index.json"
_INDEX_CACHE: list[dict] | None = None
_INDEX_MTIME: float | None = None


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def detect_page_type(url: str, title: str, text: str) -> str:
    hay = normalize(f"{url} {title} {text[:1500]}")

    if any(token in hay for token in ("orar", "/orare", "/orar")):
        return "orar"
    if any(token in hay for token in ("bursa", "burse", "/burse")):
        return "burse"
    if any(token in hay for token in ("contact", "secretariat", "/contact")):
        return "contact"
    if any(token in hay for token in ("admitere", "/admitere", "inscriere")):
        return "admitere"
    if any(token in hay for token in ("studenti", "/studenti")):
        return "studenti"
    if any(token in hay for token in ("regulament", "regulamente", "metodologie", "procedura", "proceduri")):
        return "regulamente"

    return "general"


def detect_faculty_id(url: str, faculties: list[dict]) -> str:
    host = normalize_host(url)
    for faculty in faculties:
        for base_url in faculty["base_urls"]:
            if host == normalize_host(base_url):
                return faculty["id"]

    return "uvt"


def load_index() -> list[dict]:
    global _INDEX_CACHE, _INDEX_MTIME

    if not INDEX_PATH.exists():
        _INDEX_CACHE = []
        _INDEX_MTIME = None
        return []

    mtime = INDEX_PATH.stat().st_mtime
    if _INDEX_CACHE is not None and _INDEX_MTIME == mtime:
        return list(_INDEX_CACHE)

    try:
        with INDEX_PATH.open("r", encoding="utf-8") as handle:
            items = json.load(handle)
    except (OSError, json.JSONDecodeError):
        _INDEX_CACHE = []
        _INDEX_MTIME = None
        return []

    _INDEX_CACHE = items if isinstance(items, list) else []
    _INDEX_MTIME = mtime
    return list(_INDEX_CACHE)


def save_index(items: list[dict]) -> None:
    global _INDEX_CACHE, _INDEX_MTIME

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)

    _INDEX_CACHE = list(items)
    _INDEX_MTIME = INDEX_PATH.stat().st_mtime


def get_index_status() -> dict:
    items = load_index()
    return {
        "path": str(INDEX_PATH),
        "exists": INDEX_PATH.exists(),
        "page_count": len(items),
    }
