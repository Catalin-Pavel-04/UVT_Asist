from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

INDEX_PATH = Path(__file__).with_name("data") / "page_index.json"
INDEX_META_PATH = INDEX_PATH.with_name("page_index.meta.json")
INDEX_SCHEMA_VERSION = 2
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 180
MAX_PAGE_TEXT_CHARS = max(4000, int(os.getenv("INDEX_MAX_PAGE_TEXT_CHARS", "24000")))
MAX_CHUNKS_PER_PAGE = max(1, int(os.getenv("INDEX_MAX_CHUNKS_PER_PAGE", "32")))
MAX_CHUNK_WORD_CHARS = max(200, int(os.getenv("INDEX_MAX_CHUNK_WORD_CHARS", "1000")))

_INDEX_CACHE: dict | None = None
_INDEX_MTIME: float | None = None

PATH_HINTS = {
    "orar": ("/orare", "/orar"),
    "burse": ("/burse", "/bursa"),
    "contact": ("/contact", "/secretariat"),
    "admitere": ("/admitere", "/inscriere"),
    "regulamente": ("/regulamente", "/regulament", "/metodologii", "/metodologie", "/proceduri", "/procedura"),
    "studenti": ("/studenti", "/student", "/structura-anului", "/cazare", "/cazari"),
}

TITLE_KEYWORDS = {
    "orar": ("orar", "orare"),
    "burse": ("bursa", "burse", "burselor"),
    "contact": ("contact", "secretariat"),
    "admitere": ("admitere", "inscriere"),
    "regulamente": ("regulament", "regulamente", "metodologie", "metodologii", "procedura", "proceduri", "anexa"),
    "studenti": ("studenti", "student", "studentweb", "cazare", "camine", "cămine", "taxe", "structura anului", "anului universitar"),
}

CONTENT_KEYWORDS = {
    "orar": ("orar", "orare", "programarea cursurilor"),
    "burse": ("bursa", "burse", "burselor", "sprijin financiar"),
    "contact": ("secretariat", "program cu publicul", "telefon", "e-mail"),
    "admitere": ("admitere", "inscriere", "candidat", "dosar"),
    "regulamente": ("regulament", "metodologie", "procedura", "hotarare", "anexa"),
    "studenti": ("studenti", "studentweb", "cazare", "camine", "cămine", "taxe", "structura anului universitar"),
}

GENERIC_TITLES = {
    "acasa",
    "acasa - uvt",
    "home",
    "home - uvt",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat()


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text).lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip()


def normalize_chunk_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def bound_index_text(value, max_chars: int = MAX_PAGE_TEXT_CHARS) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:max_chars]
    return str(value)[:max_chars]


def normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip()
    return host[4:] if host.startswith("www.") else host


def normalize_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    host = normalize_host(str(url))
    if not host:
        return ""

    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    path = path.rstrip("/") or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"https://{host}{path}{query}"


def _score_keyword_matches(haystack: str, keywords: tuple[str, ...], weight: int) -> int:
    return sum(weight for keyword in keywords if keyword in haystack)


def detect_page_type(url: str, title: str, text: str) -> str:
    path = normalize(urlparse(url).path or "/")
    title_norm = normalize(title)
    content_head = normalize(str(text)[:2200])
    scores = {page_type: 0 for page_type in TITLE_KEYWORDS}

    for page_type, hints in PATH_HINTS.items():
        if any(hint in path for hint in hints):
            scores[page_type] += 24

    for page_type, keywords in TITLE_KEYWORDS.items():
        scores[page_type] += _score_keyword_matches(title_norm, keywords, 12)

    if any(term in title_norm for term in ("regulament", "metodologie", "procedura", "anexa")):
        scores["regulamente"] += 30

    for page_type, keywords in CONTENT_KEYWORDS.items():
        scores[page_type] += _score_keyword_matches(content_head, keywords, 3)

    if "program" in content_head and "secretariat" in content_head:
        scores["contact"] += 10
    if "metodologie" in title_norm and "burs" in f"{title_norm} {content_head}":
        scores["regulamente"] += 18
    if "reguli de cumulare" in content_head or "art. 5" in content_head:
        scores["regulamente"] += 18
    if title_norm in GENERIC_TITLES and path == "/":
        return "general"

    best_page_type = max(scores, key=scores.get)
    return best_page_type if scores[best_page_type] > 0 else "general"


def detect_faculty_id(url: str, faculties: list[dict]) -> str:
    host = normalize_host(url)
    for faculty in faculties:
        for base_url in faculty.get("base_urls", []):
            if host == normalize_host(base_url):
                return faculty["id"]
    return "uvt"


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_chunks: int = MAX_CHUNKS_PER_PAGE,
) -> list[str]:
    chunk_size = max(200, int(chunk_size or DEFAULT_CHUNK_SIZE))
    overlap = max(0, min(int(overlap or 0), chunk_size // 2))
    max_chunks = max(1, int(max_chunks or MAX_CHUNKS_PER_PAGE))
    cleaned = re.sub(r"\s+", " ", bound_index_text(text)).strip()
    if not cleaned:
        return []

    max_word_chars = min(MAX_CHUNK_WORD_CHARS, chunk_size)
    words = [word[:max_word_chars] for word in cleaned.split(" ") if word]
    chunks: list[str] = []
    start = 0

    while start < len(words) and len(chunks) < max_chunks:
        current_words: list[str] = []
        current_length = 0
        end = start

        while end < len(words):
            word = words[end]
            additional_length = len(word) if not current_words else len(word) + 1
            if current_words and current_length + additional_length > chunk_size:
                break
            current_words.append(word)
            current_length += additional_length
            end += 1

        if not current_words:
            break

        chunk = " ".join(current_words).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break

        overlap_length = 0
        overlap_start = end
        while overlap_start > start:
            previous_word = words[overlap_start - 1]
            overlap_length += len(previous_word) + 1
            if overlap_length > overlap:
                break
            overlap_start -= 1
        next_start = overlap_start if overlap_start < end else end
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def _build_chunk_id(url: str, position: int, text: str = "", salt: str = "") -> str:
    text_digest = hashlib.sha1(normalize_chunk_text(text).encode("utf-8")).hexdigest()[:12] if text else ""
    digest = hashlib.sha1(f"{normalize_url(url)}::{position}::{text_digest}::{salt}".encode("utf-8")).hexdigest()
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
        text = bound_index_text(page.get("text")).strip()
        if not url or not text:
            continue

        title = str(page.get("title") or url).strip() or url
        faculty_id = page.get("faculty_id") or detect_faculty_id(url, faculties)
        detected_page_type = detect_page_type(url, title, text)
        page_type = detected_page_type if detected_page_type != "general" else page.get("page_type") or "general"

        for position, chunk in enumerate(chunk_text(text), start=1):
            chunks.append({
                "chunk_id": _build_chunk_id(url, position, chunk),
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
    page_urls = {normalize_url(page.get("url", "")) for page in pages if normalize_url(page.get("url", ""))}

    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "built_at": timestamp,
        "page_count": len(page_urls),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


def _empty_index() -> dict:
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "built_at": None,
        "page_count": 0,
        "chunk_count": 0,
        "chunks": [],
    }


def index_metadata(document: dict) -> dict:
    chunks = document.get("chunks", [])
    return {
        "path": str(INDEX_PATH),
        "exists": INDEX_PATH.exists(),
        "schema_version": document.get("schema_version"),
        "built_at": document.get("built_at"),
        "page_count": document.get("page_count") or len({chunk.get("url") for chunk in chunks if chunk.get("url")}),
        "chunk_count": document.get("chunk_count") or len(chunks),
        "legacy_format": bool(document.get("legacy_format")),
    }


def metadata_index_document(metadata: dict) -> dict:
    return {
        "schema_version": metadata.get("schema_version") or INDEX_SCHEMA_VERSION,
        "built_at": metadata.get("built_at"),
        "page_count": metadata.get("page_count") or 0,
        "chunk_count": metadata.get("chunk_count") or 0,
        "chunks": [],
    }


def _load_index_metadata() -> dict | None:
    if not INDEX_META_PATH.exists():
        return None
    try:
        with INDEX_META_PATH.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict):
        return None
    metadata["path"] = str(INDEX_PATH)
    metadata["exists"] = INDEX_PATH.exists()
    return metadata


def save_index_metadata(document: dict) -> None:
    INDEX_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_META_PATH.open("w", encoding="utf-8") as handle:
        json.dump(index_metadata(document), handle, ensure_ascii=False, indent=2)


def _normalize_chunk(raw_chunk: dict, fallback_position: int, timestamp: str, faculties: list[dict]) -> dict | None:
    url = normalize_url(raw_chunk.get("url", ""))
    chunk_text_value = str(raw_chunk.get("chunk_text") or raw_chunk.get("text") or "").strip()
    if not url or not chunk_text_value:
        return None

    title = str(raw_chunk.get("title") or url).strip() or url
    detected_page_type = detect_page_type(url, title, chunk_text_value)
    raw_page_type = raw_chunk.get("page_type")
    strong_student_hint = any(
        hint in normalize(f"{title} {url}")
        for hint in ("structura anului", "structura-anului", "cazare", "cazari", "camine")
    )
    if detected_page_type == "studenti" and raw_page_type in {"general", "contact"} and strong_student_hint:
        page_type = detected_page_type
    else:
        page_type = raw_page_type or detected_page_type
    faculty_id = raw_chunk.get("faculty_id") or detect_faculty_id(url, faculties)

    return {
        "chunk_id": str(raw_chunk.get("chunk_id") or _build_chunk_id(url, fallback_position, chunk_text_value)),
        "faculty_id": faculty_id,
        "page_type": page_type,
        "title": title,
        "url": url,
        "chunk_text": chunk_text_value,
        "last_indexed": str(raw_chunk.get("last_indexed") or timestamp),
    }


def _normalize_loaded_document(raw_data, file_timestamp: float | None) -> dict:
    from faculties import FACULTIES

    timestamp = iso_from_timestamp(file_timestamp) if file_timestamp else utc_now_iso()

    if isinstance(raw_data, list):
        upgraded = build_index_document(raw_data, FACULTIES, built_at=timestamp)
        upgraded["legacy_format"] = True
        return upgraded

    if not isinstance(raw_data, dict):
        return _empty_index()

    if isinstance(raw_data.get("pages"), list):
        upgraded = build_index_document(raw_data["pages"], FACULTIES, built_at=timestamp)
        upgraded["legacy_format"] = True
        return upgraded

    raw_chunks = raw_data.get("chunks")
    if not isinstance(raw_chunks, list):
        return _empty_index()

    chunks: list[dict] = []
    page_urls: set[str] = set()
    built_at = str(raw_data.get("built_at") or timestamp)

    seen_content: set[tuple[str, str]] = set()
    seen_chunk_ids: set[str] = set()

    for fallback_position, raw_chunk in enumerate(raw_chunks, start=1):
        if not isinstance(raw_chunk, dict):
            continue
        chunk = _normalize_chunk(raw_chunk, fallback_position, built_at, FACULTIES)
        if not chunk:
            continue

        content_key = (chunk["url"], normalize_chunk_text(chunk["chunk_text"]))
        if content_key in seen_content:
            continue

        chunk_id = chunk["chunk_id"]
        if chunk_id in seen_chunk_ids:
            repaired_id = _build_chunk_id(chunk["url"], fallback_position, chunk["chunk_text"])
            repair_counter = 1
            while repaired_id in seen_chunk_ids:
                repair_counter += 1
                repaired_id = _build_chunk_id(chunk["url"], fallback_position, chunk["chunk_text"], str(repair_counter))
            chunk = {**chunk, "chunk_id": repaired_id}

        seen_content.add(content_key)
        seen_chunk_ids.add(chunk["chunk_id"])
        chunks.append(chunk)
        page_urls.add(chunk["url"])

    normalized_document = {
        "schema_version": int(raw_data.get("schema_version") or INDEX_SCHEMA_VERSION),
        "built_at": built_at,
        "page_count": int(raw_data.get("page_count") or len(page_urls)),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    if raw_data.get("index_error_count"):
        normalized_document["index_error_count"] = int(raw_data.get("index_error_count") or 0)
    if isinstance(raw_data.get("index_errors"), list):
        normalized_document["index_errors"] = raw_data["index_errors"][:100]
    return normalized_document


def normalize_index_document(document: dict) -> dict:
    return _normalize_loaded_document(document, None)


def load_index() -> dict:
    global _INDEX_CACHE, _INDEX_MTIME

    if not INDEX_PATH.exists():
        empty = _empty_index()
        _INDEX_CACHE = empty
        _INDEX_MTIME = None
        return dict(empty)

    mtime = INDEX_PATH.stat().st_mtime
    if _INDEX_CACHE is not None and _INDEX_MTIME == mtime:
        return {**_INDEX_CACHE, "chunks": list(_INDEX_CACHE.get("chunks", []))}

    try:
        with INDEX_PATH.open("r", encoding="utf-8") as handle:
            raw_data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        empty = _empty_index()
        _INDEX_CACHE = empty
        _INDEX_MTIME = None
        return dict(empty)

    document = _normalize_loaded_document(raw_data, mtime)
    _INDEX_CACHE = document
    _INDEX_MTIME = mtime
    return {**document, "chunks": list(document.get("chunks", []))}


def save_index(document: dict) -> None:
    global _INDEX_CACHE, _INDEX_MTIME

    normalized_document = _normalize_loaded_document(document, None)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", encoding="utf-8") as handle:
        json.dump(normalized_document, handle, ensure_ascii=False, indent=2)
    save_index_metadata(normalized_document)

    _INDEX_CACHE = normalized_document
    _INDEX_MTIME = INDEX_PATH.stat().st_mtime


def get_index_status() -> dict:
    metadata = _load_index_metadata()
    if metadata is not None:
        return metadata

    document = load_index()
    save_index_metadata(document)
    return index_metadata(document)


def is_generic_page_title(title: str) -> bool:
    return normalize(title) in GENERIC_TITLES
