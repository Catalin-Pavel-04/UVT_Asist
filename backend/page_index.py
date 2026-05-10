from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

INDEX_PATH = Path(__file__).with_name("data") / "page_index.json"
INDEX_SCHEMA_VERSION = 2
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 180

_INDEX_CACHE: dict | None = None
_INDEX_MTIME: float | None = None

PAGE_TYPE_PRIORITY_PATHS = {
    "orar": ("/orare", "/orar"),
    "burse": ("/burse",),
    "contact": ("/contact", "/secretariat"),
    "admitere": ("/admitere", "/inscriere"),
    "regulamente": ("/regulamente", "/regulament", "/metodologii", "/metodologie", "/proceduri", "/procedura"),
    "studenti": ("/studenti",),
}

PAGE_TYPE_KEYWORDS = {
    "orar": ("orar", "orare", "orarul", "orarului"),
    "burse": ("bursa", "burse", "bursa sociala", "bursa de merit"),
    "contact": ("contact", "secretariat", "secretar", "program cu publicul", "programul secretariatului"),
    "admitere": ("admitere", "inscriere", "inscrieri", "dosar", "concurs de admitere"),
    "regulamente": ("regulament", "regulamente", "metodologie", "metodologii", "procedura", "proceduri", "anexa", "hotarare"),
    "studenti": ("studenti", "student", "studentesc", "experienta uvt"),
}

GENERIC_TITLES = {
    "acasa - uvt",
    "home - uvt",
    "home",
    "acasa",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat()


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text).lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = "https"
    host = normalize_host(url)
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"

    path = path.rstrip("/") or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{host}{path}{query}"


def detect_page_type(url: str, title: str, text: str) -> str:
    haystack = normalize(f"{url} {title} {text[:2500]}")
    path = normalize(urlparse(url).path or "/")
    title_norm = normalize(title)
    scores = {page_type: 0 for page_type in PAGE_TYPE_KEYWORDS}

    for page_type, keywords in PAGE_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in haystack:
                scores[page_type] += 2
            if keyword in title_norm:
                scores[page_type] += 3

    for page_type, path_hints in PAGE_TYPE_PRIORITY_PATHS.items():
        for hint in path_hints:
            if hint in path:
                scores[page_type] += 10

    if "secretariat" in haystack:
        scores["contact"] += 6
    if any(keyword in haystack for keyword in ("se poate", "este posibil", "cumuleaza", "beneficia de")):
        scores["regulamente"] += 3
    if "/burse" in path and any(keyword in haystack for keyword in ("regulament", "metodologie", "procedura")):
        scores["regulamente"] += 4
    if "/studenti" in path:
        scores["studenti"] += 2
    if any(keyword in title_norm for keyword in ("regulament", "metodolog", "procedur")):
        scores["regulamente"] += 12
    if any(keyword in title_norm for keyword in ("contact", "secretariat")):
        scores["contact"] += 8

    best_page_type = max(scores, key=scores.get)
    return best_page_type if scores[best_page_type] > 0 else "general"


def detect_faculty_id(url: str, faculties: list[dict]) -> str:
    host = normalize_host(url)

    for faculty in faculties:
        for base_url in faculty["base_urls"]:
            if host == normalize_host(base_url):
                return faculty["id"]

    return "uvt"


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return []

    words = cleaned.split(" ")
    chunks: list[str] = []
    start = 0

    while start < len(words):
        current_words: list[str] = []
        current_length = 0
        end = start

        while end < len(words):
            word = words[end]
            additional = len(word) if not current_words else len(word) + 1
            if current_words and current_length + additional > chunk_size:
                break

            current_words.append(word)
            current_length += additional
            end += 1

        if not current_words:
            current_words.append(words[end])
            end += 1

        chunk = " ".join(current_words).strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(words):
            break

        overlap_length = 0
        overlap_start = end
        while overlap_start > start:
            candidate_word = words[overlap_start - 1]
            overlap_length += len(candidate_word) + 1
            if overlap_length > overlap:
                break
            overlap_start -= 1

        start = overlap_start if overlap_start < end else end

    return chunks


def _build_chunk_id(url: str, position: int) -> str:
    digest = hashlib.sha1(f"{normalize_url(url)}::{position}".encode("utf-8")).hexdigest()
    return digest[:16]


def build_chunk_entries_from_pages(
    pages: list[dict],
    faculties: list[dict],
    built_at: str | None = None,
) -> list[dict]:
    timestamp = built_at or utc_now_iso()
    chunks: list[dict] = []

    for page in pages:
        url = normalize_url(page.get("url", ""))
        title = str(page.get("title") or url).strip() or url
        text = str(page.get("text") or "").strip()
        if not url or not text:
            continue

        faculty_id = page.get("faculty_id") or detect_faculty_id(url, faculties)
        page_type = detect_page_type(url, title, text)

        for position, chunk in enumerate(chunk_text(text), start=1):
            chunks.append({
                "chunk_id": _build_chunk_id(url, position),
                "faculty_id": faculty_id,
                "page_type": page_type,
                "title": title,
                "url": url,
                "chunk_text": chunk,
                "last_indexed": timestamp,
            })

    return chunks


def build_index_document(
    pages: list[dict],
    faculties: list[dict],
    built_at: str | None = None,
) -> dict:
    timestamp = built_at or utc_now_iso()
    chunks = build_chunk_entries_from_pages(pages, faculties, built_at=timestamp)
    page_urls = {normalize_url(page.get("url", "")) for page in pages if page.get("url")}

    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "built_at": timestamp,
        "page_count": len(page_urls),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


def _normalize_loaded_document(raw_data, file_timestamp: float | None) -> dict:
    from faculties import FACULTIES

    timestamp = iso_from_timestamp(file_timestamp) if file_timestamp else utc_now_iso()

    if isinstance(raw_data, dict):
        raw_chunks = raw_data.get("chunks")
        if isinstance(raw_chunks, list):
            chunks = []
            page_urls = set()

            for chunk in raw_chunks:
                if not isinstance(chunk, dict):
                    continue

                url = normalize_url(chunk.get("url", ""))
                title = str(chunk.get("title") or url).strip() or url
                chunk_text_value = str(chunk.get("chunk_text") or chunk.get("text") or "").strip()
                if not url or not chunk_text_value:
                    continue

                page_type = chunk.get("page_type") or detect_page_type(url, title, chunk_text_value)
                faculty_id = chunk.get("faculty_id") or detect_faculty_id(url, FACULTIES)
                chunk_id = str(chunk.get("chunk_id") or _build_chunk_id(url, len(chunks) + 1))
                last_indexed = str(chunk.get("last_indexed") or raw_data.get("built_at") or timestamp)

                chunks.append({
                    "chunk_id": chunk_id,
                    "faculty_id": faculty_id,
                    "page_type": page_type,
                    "title": title,
                    "url": url,
                    "chunk_text": chunk_text_value,
                    "last_indexed": last_indexed,
                })
                page_urls.add(url)

            built_at = str(raw_data.get("built_at") or timestamp)
            return {
                "schema_version": int(raw_data.get("schema_version") or INDEX_SCHEMA_VERSION),
                "built_at": built_at,
                "page_count": int(raw_data.get("page_count") or len(page_urls)),
                "chunk_count": int(raw_data.get("chunk_count") or len(chunks)),
                "chunks": chunks,
            }

        page_items = raw_data.get("pages")
        if isinstance(page_items, list):
            upgraded = build_index_document(page_items, FACULTIES, built_at=timestamp)
            upgraded["legacy_format"] = True
            return upgraded

    if isinstance(raw_data, list):
        upgraded = build_index_document(raw_data, FACULTIES, built_at=timestamp)
        upgraded["legacy_format"] = True
        return upgraded

    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "built_at": timestamp,
        "page_count": 0,
        "chunk_count": 0,
        "chunks": [],
    }


def load_index() -> dict:
    global _INDEX_CACHE, _INDEX_MTIME

    if not INDEX_PATH.exists():
        empty_index = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "built_at": None,
            "page_count": 0,
            "chunk_count": 0,
            "chunks": [],
        }
        _INDEX_CACHE = empty_index
        _INDEX_MTIME = None
        return dict(empty_index)

    mtime = INDEX_PATH.stat().st_mtime
    if _INDEX_CACHE is not None and _INDEX_MTIME == mtime:
        return {
            **_INDEX_CACHE,
            "chunks": list(_INDEX_CACHE.get("chunks", [])),
        }

    try:
        with INDEX_PATH.open("r", encoding="utf-8") as handle:
            raw_data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        empty_index = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "built_at": None,
            "page_count": 0,
            "chunk_count": 0,
            "chunks": [],
        }
        _INDEX_CACHE = empty_index
        _INDEX_MTIME = None
        return dict(empty_index)

    normalized_document = _normalize_loaded_document(raw_data, mtime)
    _INDEX_CACHE = normalized_document
    _INDEX_MTIME = mtime
    return {
        **normalized_document,
        "chunks": list(normalized_document.get("chunks", [])),
    }


def save_index(document: dict) -> None:
    global _INDEX_CACHE, _INDEX_MTIME

    normalized_document = _normalize_loaded_document(document, None)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", encoding="utf-8") as handle:
        json.dump(normalized_document, handle, ensure_ascii=False, indent=2)

    _INDEX_CACHE = normalized_document
    _INDEX_MTIME = INDEX_PATH.stat().st_mtime


def get_index_status() -> dict:
    document = load_index()
    chunks = document.get("chunks", [])
    unique_urls = {chunk.get("url") for chunk in chunks if chunk.get("url")}

    return {
        "path": str(INDEX_PATH),
        "exists": INDEX_PATH.exists(),
        "schema_version": document.get("schema_version"),
        "built_at": document.get("built_at"),
        "page_count": document.get("page_count") or len(unique_urls),
        "chunk_count": document.get("chunk_count") or len(chunks),
        "legacy_format": bool(document.get("legacy_format")),
    }


def is_generic_page_title(title: str) -> bool:
    return normalize(title) in GENERIC_TITLES
