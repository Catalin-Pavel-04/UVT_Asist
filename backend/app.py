from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS

from faculties import FACULTIES
from ollama_client import ask_ollama, get_ollama_status
from page_index import build_chunk_entries_from_pages, get_index_status, load_index
from prompts import SYSTEM_PROMPT, build_user_prompt
from retriever import (
    compute_confidence,
    normalize as normalize_retrieval_text,
    prepare_index,
    rank_index,
    rank_runtime_chunks,
)
from site_cache import get_cache_status, verify_pages
from vector_store import get_vector_index_status

app = Flask(__name__)
CORS(app)

FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}
GENERAL_FACULTY_ID = "uvt"
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 500
LIVE_VERIFY_LIMIT = max(1, int(os.getenv("LIVE_VERIFY_LIMIT", "2")))
RESPONSE_CACHE_TTL = max(60, int(os.getenv("CHAT_RESPONSE_CACHE_TTL", "300")))

LOG_FILE = Path(__file__).with_name("feedback_log.jsonl")
FEEDBACK_LOCK = threading.Lock()
RESPONSE_CACHE_LOCK = threading.Lock()
RESPONSE_CACHE: dict[str, dict] = {}

FACULTY_EXTRA_ALIASES = {
    "info": {"fmi", "mate-info", "mate info", "fac de info", "facultatea de info", "informatica"},
}

SPECIFIC_QUERY_HINTS = {
    "admitere",
    "bursa",
    "burse",
    "cazare",
    "contact",
    "email",
    "metodologie",
    "orar",
    "orare",
    "procedura",
    "program",
    "regulament",
    "secretariat",
    "taxe",
    "telefon",
}

VAGUE_QUESTIONS = {
    "ajutor",
    "asta",
    "ceva",
    "despre asta",
    "detalii",
    "informatii",
    "mai multe",
}

BAD_GENERATION_MARKERS = (
    "okay,",
    "let me",
    "the student is asking",
    "retrieved context",
    "source 1",
    "first, i",
    "i check",
    "i'll check",
)


@dataclass(frozen=True)
class ChatRequest:
    question: str
    requested_faculty_id: str
    history: list[dict]


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "llm_provider": "ollama",
        "embedding_provider": "ollama",
        "retrieval_mode": "qdrant-vector-rag",
        "ollama": get_ollama_status(),
        "index": get_index_status(),
        "vector_index": get_vector_index_status(),
        "verification_cache": get_cache_status(),
        "response_cache_entries": get_response_cache_size(),
    })


@app.get("/faculties")
def faculties():
    return jsonify({
        "faculties": [
            {"id": faculty["id"], "name": faculty["name"]}
            for faculty in FACULTIES
        ]
    })


def normalize_match_text(text: str) -> str:
    normalized = normalize_retrieval_text(text)
    normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def build_faculty_aliases() -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}

    for faculty in FACULTIES:
        if faculty["id"] == GENERAL_FACULTY_ID:
            continue

        normalized_name = normalize_match_text(faculty["name"])
        short_name = normalized_name.replace("facultatea ", "", 1).strip()
        faculty_aliases = {faculty["id"], normalized_name, short_name}
        faculty_aliases.update(FACULTY_EXTRA_ALIASES.get(faculty["id"], set()))

        for base_url in faculty.get("base_urls", []):
            host = (urlparse(base_url).hostname or "").lower()
            if host.startswith("www."):
                host = host[4:]
            if host:
                faculty_aliases.add(host.split(".")[0])

        aliases[faculty["id"]] = {alias for alias in faculty_aliases if alias}

    return aliases


FACULTY_ALIASES = build_faculty_aliases()


def parse_chat_request(payload: dict) -> ChatRequest:
    return ChatRequest(
        question=str(payload.get("question") or "").strip(),
        requested_faculty_id=str(payload.get("faculty_id") or GENERAL_FACULTY_ID).strip(),
        history=normalize_history(payload.get("history")),
    )


def normalize_history(history) -> list[dict]:
    if not isinstance(history, list):
        return []

    normalized_history: list[dict] = []
    for item in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue

        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue

        content = " ".join(str(item.get("content", "")).split()).strip()
        if content:
            normalized_history.append({"role": role, "content": content[:MAX_HISTORY_CHARS]})

    return normalized_history


def get_faculty(faculty_id: str) -> dict:
    return FACULTY_MAP.get(faculty_id, FACULTY_MAP[GENERAL_FACULTY_ID])


def infer_faculty(requested_faculty_id: str, question: str, history: list[dict]) -> dict:
    selected_faculty = get_faculty(requested_faculty_id)
    if selected_faculty["id"] != GENERAL_FACULTY_ID:
        return selected_faculty

    candidate_texts = [question]
    candidate_texts.extend(item.get("content", "") for item in reversed(history))

    for text in candidate_texts:
        normalized_text = f" {normalize_match_text(text)} "
        if not normalized_text.strip():
            continue

        for faculty_id, aliases in FACULTY_ALIASES.items():
            for alias in aliases:
                if len(alias) >= 3 and f" {alias} " in normalized_text:
                    return FACULTY_MAP[faculty_id]

    return selected_faculty


def token_matches_specific_hint(token: str) -> bool:
    return any(token == hint or token.startswith(hint) or hint.startswith(token) for hint in SPECIFIC_QUERY_HINTS)


def is_vague_question(question: str) -> bool:
    normalized_question = normalize_match_text(question)
    if not normalized_question or normalized_question in VAGUE_QUESTIONS:
        return True

    tokens = [token for token in normalized_question.split() if len(token) >= 3]
    if any(token_matches_specific_hint(token) for token in tokens):
        return False
    return len(tokens) <= 2


def build_effective_question(question: str, history: list[dict]) -> str:
    if not is_vague_question(question):
        return question

    context = [item["content"] for item in history[-3:] if item.get("content")]
    context.append(question)
    return " ".join(context)


def get_response_cache_size() -> int:
    now = time.time()
    with RESPONSE_CACHE_LOCK:
        return sum(1 for item in RESPONSE_CACHE.values() if now - item["timestamp"] < RESPONSE_CACHE_TTL)


def build_cache_key(
    faculty_id: str,
    effective_question: str,
    history: list[dict],
    index_built_at: str | None,
    vector_points_count: int | None,
) -> str:
    payload = {
        "faculty_id": faculty_id,
        "question": normalize_match_text(effective_question),
        "history": history[-2:],
        "index_built_at": index_built_at,
        "vector_points_count": vector_points_count,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def get_cached_response(cache_key: str) -> dict | None:
    now = time.time()
    with RESPONSE_CACHE_LOCK:
        cached = RESPONSE_CACHE.get(cache_key)
        if cached and now - cached["timestamp"] < RESPONSE_CACHE_TTL:
            return cached["response"]
    return None


def set_cached_response(cache_key: str, response_payload: dict) -> None:
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = {"timestamp": time.time(), "response": response_payload}


def merge_ranked_chunks(primary_chunks: list[dict], verified_chunks: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}

    for chunk in primary_chunks + verified_chunks:
        url = chunk.get("url")
        chunk_text = chunk.get("chunk_text")
        if not url or not chunk_text:
            continue

        key = (url, str(chunk_text)[:180])
        previous = merged.get(key)
        if previous is None or chunk.get("retrieval_score", 0) > previous.get("retrieval_score", 0):
            merged[key] = dict(chunk)
        elif chunk.get("verified"):
            previous["verified"] = True

    return sorted(merged.values(), key=lambda item: item.get("retrieval_score", 0), reverse=True)


def unique_sources_from_chunks(chunks: list[dict]) -> list[dict]:
    seen: set[str] = set()
    sources: list[dict] = []

    for chunk in chunks:
        url = chunk.get("url", "")
        if not url or url in seen:
            continue

        sources.append({
            "title": chunk.get("title", url),
            "url": url,
            "faculty_id": chunk.get("faculty_id", GENERAL_FACULTY_ID),
            "page_type": chunk.get("page_type", "general"),
            "verified": bool(chunk.get("verified")),
        })
        seen.add(url)

    return sources


def build_local_fallback_answer(retrieval_result: dict) -> str:
    chunks = retrieval_result.get("chunks", [])
    if not chunks:
        return "Nu am gasit suficiente dovezi oficiale in indexul local pentru un raspuns sigur."

    best_chunk = chunks[0]
    title = best_chunk.get("title", "sursa oficiala")
    url = best_chunk.get("url", "")
    snippet = " ".join(str(best_chunk.get("chunk_text", "")).split())
    if len(snippet) > 420:
        snippet = snippet[:420].rsplit(" ", 1)[0].strip()

    if retrieval_result.get("confidence") == "low":
        return (
            "Am gasit doar dovezi partiale in sursele oficiale. "
            f"Cea mai relevanta pagina este \"{title}\"."
        )

    if snippet:
        return f"Cea mai relevanta sursa oficiala este \"{title}\" ({url}). Fragment util: {snippet}..."
    return f"Cea mai relevanta sursa oficiala este \"{title}\" ({url})."


def answer_needs_fallback(answer: str) -> bool:
    head = " ".join(str(answer).split()).lower()[:900]
    return any(marker in head for marker in BAD_GENERATION_MARKERS)


def live_verify_retrieval(
    effective_question: str,
    faculty_id: str,
    retrieval_result: dict,
    index_document: dict,
) -> tuple[list[dict], bool]:
    top_urls = [chunk.get("url") for chunk in retrieval_result.get("chunks", []) if chunk.get("url")]
    verified_pages = verify_pages(top_urls, max_pages=LIVE_VERIFY_LIMIT)
    if not verified_pages:
        return retrieval_result.get("chunks", []), False

    verified_chunks = build_chunk_entries_from_pages(verified_pages, FACULTIES)
    prepared_index = prepare_index(index_document)
    verified_result = rank_runtime_chunks(
        verified_chunks,
        effective_question,
        faculty_id,
        idf=prepared_index.get("idf", {}),
        top_k=4,
    )
    verified_urls = {page.get("url") for page in verified_pages if page.get("url")}
    merged_chunks = merge_ranked_chunks(retrieval_result.get("chunks", []), verified_result.get("chunks", []))

    for chunk in merged_chunks:
        if chunk.get("url") in verified_urls:
            chunk["verified"] = True

    return merged_chunks[:6], True


def refresh_confidence(retrieval_result: dict, chunks: list[dict]) -> None:
    confidence = compute_confidence(chunks[:4], retrieval_result.get("analysis"))
    retrieval_result["chunks"] = chunks[:4]
    retrieval_result["confidence"] = confidence["label"]
    retrieval_result["confidence_score"] = confidence["score"]
    retrieval_result["confidence_reason"] = confidence["reason"]


def build_response_payload(answer: str, faculty: dict, retrieval_result: dict, live_verified: bool) -> dict:
    analysis = retrieval_result.get("analysis", {})
    return {
        "answer": answer,
        "sources": unique_sources_from_chunks(retrieval_result.get("chunks", [])),
        "matched_faculty": faculty["name"],
        "matched_faculty_id": faculty["id"],
        "confidence": retrieval_result.get("confidence", "low"),
        "confidence_score": retrieval_result.get("confidence_score", 0),
        "confidence_reason": retrieval_result.get("confidence_reason", ""),
        "live_verified": live_verified,
        "query_profile": {
            "intent": analysis.get("intent", "general"),
            "policy_question": bool(analysis.get("is_policy_question", False)),
            "normalized_question": analysis.get("corrected_question", ""),
            "corrections": analysis.get("corrections", []),
        },
        "retrieval_backend": retrieval_result.get("retrieval_backend", "unknown"),
    }


def empty_question_payload() -> dict:
    return {
        "answer": "Intrebarea este goala.",
        "sources": [],
        "matched_faculty": FACULTY_MAP[GENERAL_FACULTY_ID]["name"],
        "matched_faculty_id": GENERAL_FACULTY_ID,
        "confidence": "low",
        "confidence_score": 0,
        "confidence_reason": "Nu a fost primita nicio intrebare.",
        "live_verified": False,
        "query_profile": {
            "intent": "general",
            "policy_question": False,
            "normalized_question": "",
            "corrections": [],
        },
        "retrieval_backend": "none",
    }


@app.post("/chat")
def chat():
    chat_request = parse_chat_request(request.get_json(silent=True) or {})
    if not chat_request.question:
        return jsonify(empty_question_payload())

    faculty = infer_faculty(chat_request.requested_faculty_id, chat_request.question, chat_request.history)
    effective_question = build_effective_question(chat_request.question, chat_request.history)
    question_is_vague = is_vague_question(chat_request.question)
    index_document = load_index()
    vector_status = get_vector_index_status()

    cache_key = build_cache_key(
        faculty["id"],
        effective_question,
        chat_request.history,
        index_document.get("built_at"),
        vector_status.get("points_count"),
    )
    cached_response = get_cached_response(cache_key)
    if cached_response is not None:
        return jsonify(cached_response)

    retrieval_result = rank_index(effective_question, index_document, faculty["id"], top_k=6)
    live_verified = False

    if retrieval_result.get("chunks"):
        merged_chunks, live_verified = live_verify_retrieval(
            effective_question,
            faculty["id"],
            retrieval_result,
            index_document,
        )
        refresh_confidence(retrieval_result, merged_chunks)

    prompt = build_user_prompt(
        chat_request.question,
        faculty["name"],
        retrieval_result,
        history=chat_request.history,
        question_is_vague=question_is_vague,
    )

    try:
        answer = ask_ollama(SYSTEM_PROMPT, prompt)
        if answer_needs_fallback(answer):
            answer = build_local_fallback_answer(retrieval_result)
    except Exception:
        answer = build_local_fallback_answer(retrieval_result)

    response_payload = build_response_payload(answer, faculty, retrieval_result, live_verified)
    set_cached_response(cache_key, response_payload)
    return jsonify(response_payload)


def append_feedback_record(payload: dict) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "question": payload.get("question"),
        "selected_faculty": payload.get("faculty_id"),
        "matched_faculty": payload.get("matched_faculty"),
        "answer": payload.get("answer"),
        "confidence": payload.get("confidence"),
        "confidence_score": payload.get("confidence_score"),
        "feedback_vote": payload.get("feedback"),
        "sources": payload.get("sources", []),
        "source": payload.get("source", "popup"),
        "live_verified": bool(payload.get("live_verified")),
        "retrieval_backend": payload.get("retrieval_backend"),
    }

    with FEEDBACK_LOCK:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.post("/feedback")
def feedback():
    append_feedback_record(request.get_json(silent=True) or {})
    return jsonify({"ok": True})


def flask_debug_enabled() -> bool:
    return os.getenv("FLASK_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    debug = flask_debug_enabled()
    app.run(host="127.0.0.1", port=5000, debug=debug, use_reloader=debug)
