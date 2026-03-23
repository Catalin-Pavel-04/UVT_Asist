import os
import re
import unicodedata
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor
from flask_cors import CORS
from urllib.parse import urljoin, urlparse

from faculties import FACULTIES
from live_fetch import fetch_page, extract_candidate_links
from retriever import rank_chunks, rank_prebuilt_chunks
from prompts import SYSTEM_PROMPT, build_user_prompt
from llm_client import ask_llm
from site_cache import ensure_background_refresh_started, get_cache_status, get_cached_chunks

app = Flask(__name__)
CORS(app)

FACULTY_MAP = {f["id"]: f for f in FACULTIES}
NON_GENERAL_FACULTIES = [faculty for faculty in FACULTIES if faculty["id"] != "uvt"]

PRIORITY_PATHS = [
    "/orare/",
    "/orar/",
    "/studenti/",
    "/contact/",
    "/admitere/",
    "/burse/",
    "/secretariat/"
]

QUESTION_PATH_HINTS = {
    "orar": ("/orare/", "/orar/"),
    "burs": ("/burse/",),
    "admitere": ("/admitere/",),
    "contact": ("/contact/", "/secretariat/"),
    "secretariat": ("/secretariat/", "/contact/"),
    "program": ("/contact/", "/secretariat/"),
    "student": ("/studenti/",),
}

DOCUMENT_KEYWORDS = (
    "pdf",
    "document",
    "documente",
    "fisa",
    "fișa",
    "fise",
    "fișe",
    "plan",
    "regulament",
    "metodologie",
    "formular",
    "cerere",
    "anexa",
)

DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".txt")

MAX_INITIAL_PAGES = 3
MAX_FALLBACK_PAGES = 2
FETCH_WORKERS = 4
DISCOVERY_SEED_PAGES = 4
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 500


@app.get("/health")
def health():
    ensure_background_refresh_started()
    return {
        "status": "ok",
        "llm_provider": "gemini",
        "cache": get_cache_status(),
    }


@app.get("/faculties")
def faculties():
    ensure_background_refresh_started()
    return {"faculties": [{"id": f["id"], "name": f["name"]} for f in FACULTIES]}


def score_candidate_url(question: str, url: str, base_urls: list[str]) -> int:
    score = 0
    question_text = question.lower()
    normalized_url = url.lower()

    if url in base_urls:
        score += 4

    for token, paths in QUESTION_PATH_HINTS.items():
        if token not in question_text:
            continue

        if any(path in normalized_url for path in paths):
            score += 10

    if any(keyword in question_text for keyword in DOCUMENT_KEYWORDS):
        if normalized_url.endswith(DOCUMENT_EXTENSIONS):
            score += 12

    return score


def get_candidate_pages(faculty_id: str, question: str) -> list[str]:
    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    base_urls = faculty["base_urls"]

    candidates = []

    for base in base_urls:
        candidates.append(base)

        for path in PRIORITY_PATHS:
            candidates.append(urljoin(base, path.lstrip("/")))

    seen = set()
    unique = []

    for url in candidates:
        if url not in seen:
            unique.append(url)
            seen.add(url)

    unique.sort(
        key=lambda url: score_candidate_url(question, url, base_urls),
        reverse=True,
    )
    return unique[:20]


def discover_candidate_pages(faculty_id: str, current_urls: list[str]) -> list[str]:
    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    base_urls = faculty["base_urls"]
    discovered = []
    seen = set(current_urls)

    seed_urls = []

    for url in current_urls:
        if url.lower().endswith(DOCUMENT_EXTENSIONS):
            continue

        seed_urls.append(url)
        if len(seed_urls) >= DISCOVERY_SEED_PAGES:
            break

    for base in base_urls:
        if base not in seed_urls:
            seed_urls.append(base)

    for seed_url in seed_urls:
        for url in extract_candidate_links(seed_url, base_urls, max_links=12):
            if url in seen:
                continue

            discovered.append(url)
            seen.add(url)

    return discovered


def question_needs_documents(question: str) -> bool:
    question_text = question.lower()
    return any(keyword in question_text for keyword in DOCUMENT_KEYWORDS)


def select_document_urls(urls: list[str], question: str, faculty_id: str, max_urls: int = 2) -> list[str]:
    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    base_urls = faculty["base_urls"]
    document_urls = [url for url in urls if url.lower().endswith(DOCUMENT_EXTENSIONS)]
    document_urls.sort(
        key=lambda url: score_candidate_url(question, url, base_urls),
        reverse=True,
    )
    return document_urls[:max_urls]


def fetch_pages(urls: list[str], max_pages: int) -> list[dict]:
    selected = urls[:max_pages]
    if not selected:
        return []

    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(selected))) as executor:
        pages = list(executor.map(fetch_page, selected))

    return [page for page in pages if page.get("text")]


def unique_sources_from_chunks(chunks: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for c in chunks:
        url = c.get("url", "")
        if not url or url in seen:
            continue

        result.append({
            "title": c.get("title", url),
            "url": url
        })
        seen.add(url)

    return result


def get_faculty(faculty_id: str) -> dict:
    return FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])


def normalize_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def build_faculty_aliases() -> dict[str, set[str]]:
    aliases = {}

    for faculty in NON_GENERAL_FACULTIES:
        normalized_name = normalize_match_text(faculty["name"])
        normalized_short_name = normalized_name.replace("facultatea ", "", 1).strip()
        faculty_aliases = {
            faculty["id"],
            normalized_name,
            normalized_short_name,
        }

        for base_url in faculty["base_urls"]:
            hostname = (urlparse(base_url).hostname or "").lower()
            if hostname.startswith("www."):
                hostname = hostname[4:]

            if hostname:
                faculty_aliases.add(hostname.split(".")[0])

        aliases[faculty["id"]] = {alias for alias in faculty_aliases if alias}

    return aliases


FACULTY_ALIASES = build_faculty_aliases()


def normalize_history(history) -> list[dict]:
    if not isinstance(history, list):
        return []

    normalized = []

    for item in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue

        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue

        content = " ".join(str(item.get("content", "")).split()).strip()
        if not content:
            continue

        normalized.append({
            "role": role,
            "content": content[:MAX_HISTORY_CHARS],
        })

    return normalized


def infer_faculty(requested_faculty_id: str, question: str, history: list[dict]) -> dict:
    selected_faculty = get_faculty(requested_faculty_id)
    if selected_faculty["id"] != "uvt":
        return selected_faculty

    candidate_texts = [question]
    candidate_texts.extend(item.get("content", "") for item in reversed(history))

    for text in candidate_texts:
        normalized_text = normalize_match_text(text)
        if not normalized_text:
            continue

        for faculty_id, aliases in FACULTY_ALIASES.items():
            if normalized_text in aliases:
                return FACULTY_MAP[faculty_id]

            if any(f" {alias} " in f" {normalized_text} " for alias in aliases if len(alias) >= 3):
                return FACULTY_MAP[faculty_id]

    return selected_faculty


def build_effective_question(question: str, history: list[dict]) -> str:
    normalized_question = normalize_match_text(question)
    if len(normalized_question) >= 12 and (
        any(token in normalized_question for token in QUESTION_PATH_HINTS)
        or question_needs_documents(question)
    ):
        return question

    context_parts = [item["content"] for item in history[-3:] if item.get("content")]
    context_parts.append(question)
    return " ".join(context_parts)


def normalize_base_identity(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    path = parsed.path.rstrip("/") or "/"
    return f"{hostname}{path}"


def is_base_url(url: str, base_urls: list[str]) -> bool:
    normalized_url = normalize_base_identity(url)
    normalized_bases = {normalize_base_identity(base_url) for base_url in base_urls}
    return normalized_url in normalized_bases


def top_chunks_need_specific_search(chunks: list[dict], question: str, faculty: dict) -> bool:
    normalized_question = normalize_match_text(question)
    if not any(token in normalized_question for token in QUESTION_PATH_HINTS):
        return False

    return bool(chunks) and all(is_base_url(chunk.get("url", ""), faculty["base_urls"]) for chunk in chunks)


@app.post("/chat")
def chat():
    ensure_background_refresh_started()
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    requested_faculty_id = (data.get("faculty_id") or "uvt").strip()
    history = normalize_history(data.get("history"))

    if not question:
        return jsonify({
            "answer": "Întrebarea este goală",
            "sources": [],
            "matched_faculty": FACULTY_MAP["uvt"]["name"]
        })

    faculty = infer_faculty(requested_faculty_id, question, history)
    faculty_id = faculty["id"]
    effective_question = build_effective_question(question, history)
    cached_chunks = get_cached_chunks(faculty_id)
    top_chunks = rank_prebuilt_chunks(effective_question, cached_chunks, top_k=3) if cached_chunks else []
    candidate_urls = get_candidate_pages(faculty_id, effective_question)
    pages = []

    if not top_chunks:
        pages = fetch_pages(candidate_urls, max_pages=MAX_INITIAL_PAGES)
        top_chunks = rank_chunks(effective_question, pages, top_k=3) if pages else []

    if not top_chunks or top_chunks_need_specific_search(top_chunks, effective_question, faculty):
        fallback_urls = discover_candidate_pages(faculty_id, candidate_urls)
        fallback_pages = fetch_pages(fallback_urls, max_pages=MAX_FALLBACK_PAGES)
        if fallback_pages:
            pages.extend(fallback_pages)
            top_chunks = rank_chunks(effective_question, pages, top_k=3)
    elif question_needs_documents(effective_question):
        if not cached_chunks:
            fallback_urls = discover_candidate_pages(faculty_id, candidate_urls)
            document_urls = select_document_urls(fallback_urls, effective_question, faculty_id)
            if document_urls:
                pages.extend(fetch_pages(document_urls, max_pages=len(document_urls)))
                top_chunks = rank_chunks(effective_question, pages, top_k=3) if pages else []

    prompt = build_user_prompt(question, faculty["name"], top_chunks, history=history)

    try:
        llm_answer = ask_llm(SYSTEM_PROMPT, prompt)
    except Exception as e:
        return jsonify({
            "answer": f"Eroare la interogarea modelului Gemini: {str(e)}",
            "sources": unique_sources_from_chunks(top_chunks),
            "matched_faculty": faculty["name"]
        })

    return jsonify({
        "answer": llm_answer,
        "sources": unique_sources_from_chunks(top_chunks),
        "matched_faculty": faculty["name"]
    })


if __name__ == "__main__":
    debug_mode = True
    if not debug_mode or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        ensure_background_refresh_started()

    app.run(host="127.0.0.1", port=5000, debug=debug_mode)
