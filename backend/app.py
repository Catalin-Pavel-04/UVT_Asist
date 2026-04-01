import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS

from faculties import FACULTIES
from live_fetch import fetch_page
from llm_client import ask_llm
from page_index import get_index_status, load_index
from prompts import SYSTEM_PROMPT, build_user_prompt
from retriever import compute_confidence, detect_intent, normalize as normalize_retrieval_text, rank_chunks, rank_index

app = Flask(__name__)
CORS(app)

FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}
NON_GENERAL_FACULTIES = [faculty for faculty in FACULTIES if faculty["id"] != "uvt"]
PRIORITY_PATHS = [
    "/orare/",
    "/orar/",
    "/studenti/",
    "/contact/",
    "/admitere/",
    "/burse/",
    "/secretariat/",
]
INTENT_PATH_HINTS = {
    "orar": ("/orare/", "/orar/"),
    "burse": ("/burse/",),
    "contact": ("/contact/", "/secretariat/"),
    "admitere": ("/admitere/",),
    "regulamente": ("/studenti/",),
}
SPECIFIC_QUERY_HINTS = {
    "orar",
    "burse",
    "bursa",
    "contact",
    "secretariat",
    "program",
    "admitere",
    "inscriere",
    "studenti",
    "regulament",
    "regulamente",
    "metodologie",
    "procedura",
    "proceduri",
    "cazare",
    "taxe",
    "taxa",
    "master",
    "licenta",
    "erasmus",
}
VAGUE_QUESTION_PATTERNS = {
    "ajutor",
    "informatii",
    "detalii",
    "mai multe",
    "ceva",
    "asta",
    "despre asta",
}

INDEX_RANK_LIMIT = 6
INITIAL_LIVE_FETCH_LIMIT = 3
EXTRA_LIVE_FETCH_LIMIT = 2
SEED_FALLBACK_LIMIT = 3
FETCH_WORKERS = 4
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 500

LOG_FILE = Path(__file__).with_name("feedback_log.jsonl")
FEEDBACK_LOCK = threading.Lock()
FACULTY_EXTRA_ALIASES = {
    "info": {"fmi", "fac de info", "facultatea de info"},
}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": "gemini",
        "index": get_index_status(),
    }


@app.get("/faculties")
def faculties():
    return {"faculties": [{"id": faculty["id"], "name": faculty["name"]} for faculty in FACULTIES]}


def unique_urls(urls: list[str]) -> list[str]:
    seen = set()
    unique = []

    for url in urls:
        if not url or url in seen:
            continue

        seen.add(url)
        unique.append(url)

    return unique


def fetch_pages(urls: list[str], max_pages: int) -> list[dict]:
    selected_urls = unique_urls(urls[:max_pages])
    if not selected_urls:
        return []

    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(selected_urls))) as executor:
        pages = list(executor.map(fetch_page, selected_urls))

    return [page for page in pages if page.get("text")]


def build_seed_candidate_urls(faculty_id: str) -> list[str]:
    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    candidates = []

    for base_url in faculty["base_urls"]:
        for path in PRIORITY_PATHS:
            candidates.append(urljoin(base_url, path.lstrip("/")))

        candidates.append(base_url)

    return unique_urls(candidates)


def score_seed_candidate_url(question: str, url: str, base_urls: list[str]) -> int:
    score = 0
    normalized_url = url.lower()
    intent = detect_intent(question)

    if url in base_urls:
        score += 2

    for path_hint in INTENT_PATH_HINTS.get(intent, ()):
        if path_hint in normalized_url:
            score += 10

    if any(priority_path in normalized_url for priority_path in PRIORITY_PATHS):
        score += 2

    return score


def rank_seed_candidate_urls(faculty_id: str, question: str) -> list[str]:
    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    base_urls = faculty["base_urls"]
    candidates = build_seed_candidate_urls(faculty_id)
    return sorted(
        candidates,
        key=lambda url: score_seed_candidate_url(question, url, base_urls),
        reverse=True,
    )


def unique_sources_from_chunks(chunks: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for chunk in chunks:
        url = chunk.get("url", "")
        if not url or url in seen:
            continue

        result.append({
            "title": chunk.get("title", url),
            "url": url,
        })
        seen.add(url)

    return result


def get_faculty(faculty_id: str) -> dict:
    return FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])


def normalize_match_text(text: str) -> str:
    normalized = normalize_retrieval_text(text)
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
        faculty_aliases.update(FACULTY_EXTRA_ALIASES.get(faculty["id"], set()))

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


def is_vague_question(question: str) -> bool:
    normalized_question = normalize_match_text(question)
    if not normalized_question:
        return True

    if normalized_question in VAGUE_QUESTION_PATTERNS:
        return True

    tokens = [token for token in normalized_question.split() if len(token) >= 3]
    if any(token_matches_specific_hint(token) for token in tokens):
        return False

    return len(tokens) <= 2


def token_matches_specific_hint(token: str) -> bool:
    return any(
        token == hint or token.startswith(hint) or hint.startswith(token)
        for hint in SPECIFIC_QUERY_HINTS
    )


def build_effective_question(question: str, history: list[dict]) -> str:
    if not is_vague_question(question):
        return question

    context_parts = [item["content"] for item in history[-3:] if item.get("content")]
    context_parts.append(question)
    return " ".join(context_parts)


def append_feedback_record(payload: dict) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "payload": payload,
    }

    with FEEDBACK_LOCK:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    requested_faculty_id = (data.get("faculty_id") or "uvt").strip()
    history = normalize_history(data.get("history"))

    if not question:
        return jsonify({
            "answer": "Intrebarea este goala",
            "sources": [],
            "matched_faculty": FACULTY_MAP["uvt"]["name"],
            "confidence": "low",
            "live_verified": False,
        })

    faculty = infer_faculty(requested_faculty_id, question, history)
    faculty_id = faculty["id"]
    question_is_vague = is_vague_question(question)
    effective_question = build_effective_question(question, history)
    index_items = load_index()
    ranked_pages = rank_index(effective_question, index_items, faculty_id, top_k=INDEX_RANK_LIMIT) if index_items else []
    candidate_urls = [item["url"] for item in ranked_pages]

    if not candidate_urls:
        candidate_urls = rank_seed_candidate_urls(faculty_id, effective_question)

    pages = fetch_pages(candidate_urls, INITIAL_LIVE_FETCH_LIMIT)
    top_chunks = rank_chunks(effective_question, pages, top_k=3) if pages else []
    confidence = compute_confidence(top_chunks)

    if confidence == "low":
        extra_urls = candidate_urls[INITIAL_LIVE_FETCH_LIMIT:INITIAL_LIVE_FETCH_LIMIT + EXTRA_LIVE_FETCH_LIMIT]
        if extra_urls:
            extra_pages = fetch_pages(extra_urls, len(extra_urls))
            if extra_pages:
                pages.extend(extra_pages)
                top_chunks = rank_chunks(effective_question, pages, top_k=3)
                confidence = compute_confidence(top_chunks)

    if confidence == "low":
        fetched_urls = {page.get("url", "") for page in pages}
        fallback_urls = [
            url
            for url in rank_seed_candidate_urls(faculty_id, effective_question)
            if url not in fetched_urls
        ]
        fallback_pages = fetch_pages(fallback_urls, SEED_FALLBACK_LIMIT)
        if fallback_pages:
            pages.extend(fallback_pages)
            top_chunks = rank_chunks(effective_question, pages, top_k=3)
            confidence = compute_confidence(top_chunks)

    prompt = build_user_prompt(
        question,
        faculty["name"],
        top_chunks,
        confidence,
        history=history,
        question_is_vague=question_is_vague,
    )

    try:
        llm_answer = ask_llm(SYSTEM_PROMPT, prompt)
    except Exception as exc:
        return jsonify({
            "answer": f"Eroare la interogarea modelului Gemini: {exc}",
            "sources": unique_sources_from_chunks(top_chunks),
            "matched_faculty": faculty["name"],
            "confidence": confidence,
            "live_verified": bool(top_chunks),
        })

    return jsonify({
        "answer": llm_answer,
        "sources": unique_sources_from_chunks(top_chunks),
        "matched_faculty": faculty["name"],
        "confidence": confidence,
        "live_verified": bool(top_chunks),
    })


@app.post("/feedback")
def feedback():
    data = request.get_json(silent=True) or {}
    append_feedback_record(data)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
