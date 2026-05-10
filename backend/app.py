import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS

from faculties import FACULTIES
from llm_client import ask_llm
from page_index import build_chunk_entries_from_pages, get_index_status, load_index
from prompts import SYSTEM_PROMPT, build_user_prompt
from retriever import (
    analyze_query,
    compute_confidence,
    normalize as normalize_retrieval_text,
    prepare_index,
    rank_index,
    rank_runtime_chunks,
)
from site_cache import get_cache_status, verify_pages

app = Flask(__name__)
CORS(app)

FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}
NON_GENERAL_FACULTIES = [faculty for faculty in FACULTIES if faculty["id"] != "uvt"]
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 500
LIVE_VERIFY_LIMIT = max(1, int(os.getenv("LIVE_VERIFY_LIMIT", "2")))
RESPONSE_CACHE_TTL = max(60, int(os.getenv("CHAT_RESPONSE_CACHE_TTL", "300")))

LOG_FILE = Path(__file__).with_name("feedback_log.jsonl")
FEEDBACK_LOCK = threading.Lock()
RESPONSE_CACHE_LOCK = threading.Lock()
RESPONSE_CACHE: dict[str, dict] = {}

FACULTY_EXTRA_ALIASES = {
    "info": {"fmi", "fac de info", "facultatea de info"},
}
SPECIFIC_QUERY_HINTS = {
    "orar",
    "burse",
    "contact",
    "secretariat",
    "admitere",
    "regulament",
    "metodologie",
    "procedura",
    "studenti",
    "taxe",
    "cazare",
    "program",
    "telefon",
    "email",
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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": "gemini",
        "retrieval_mode": "local-index-first-rag",
        "index": get_index_status(),
        "verification_cache": get_cache_status(),
        "response_cache_entries": get_response_cache_size(),
    }


@app.get("/faculties")
def faculties():
    return {"faculties": [{"id": faculty["id"], "name": faculty["name"]} for faculty in FACULTIES]}


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


def get_faculty(faculty_id: str) -> dict:
    return FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])


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


def get_response_cache_size() -> int:
    now = time.time()
    with RESPONSE_CACHE_LOCK:
        return sum(1 for item in RESPONSE_CACHE.values() if now - item["timestamp"] < RESPONSE_CACHE_TTL)


def build_cache_key(faculty_id: str, effective_question: str, history: list[dict], index_built_at: str | None) -> str:
    payload = {
        "faculty_id": faculty_id,
        "question": normalize_match_text(effective_question),
        "history": history[-2:],
        "index_built_at": index_built_at,
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
        RESPONSE_CACHE[cache_key] = {
            "timestamp": time.time(),
            "response": response_payload,
        }


def merge_ranked_chunks(primary_chunks: list[dict], verified_chunks: list[dict]) -> list[dict]:
    merged = {}

    for chunk in primary_chunks + verified_chunks:
        if not chunk.get("url") or not chunk.get("chunk_text"):
            continue

        key = (chunk["url"], chunk["chunk_text"][:160])
        previous = merged.get(key)
        if previous is None or chunk.get("retrieval_score", 0) > previous.get("retrieval_score", 0):
            merged[key] = dict(chunk)
        elif chunk.get("verified"):
            previous["verified"] = True

    merged_chunks = list(merged.values())
    merged_chunks.sort(key=lambda item: item.get("retrieval_score", 0), reverse=True)
    return merged_chunks


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
            "faculty_id": chunk.get("faculty_id", "uvt"),
            "page_type": chunk.get("page_type", "general"),
            "verified": bool(chunk.get("verified")),
        })
        seen.add(url)

    return result


def build_local_fallback_answer(retrieval_result: dict) -> str:
    chunks = retrieval_result.get("chunks", [])
    if not chunks:
        return "Nu am gasit suficiente dovezi oficiale in indexul local pentru a formula un raspuns sigur."

    best_chunk = chunks[0]
    snippet = " ".join(str(best_chunk.get("chunk_text", "")).split())
    snippet = snippet[:360].rsplit(" ", 1)[0].strip() if snippet else ""

    if retrieval_result.get("confidence") == "low":
        return (
            "Am gasit doar indicii partiale in sursele oficiale. "
            f"Cea mai relevanta pagina pare sa fie „{best_chunk.get('title', 'Sursa oficiala')}”."
        )

    if snippet:
        return (
            f"Cea mai relevanta sursa oficiala este „{best_chunk.get('title', 'Sursa oficiala')}”. "
            f"Fragment util: {snippet}..."
        )

    return f"Cea mai relevanta sursa oficiala este „{best_chunk.get('title', 'Sursa oficiala')}”."


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
    }

    with FEEDBACK_LOCK:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


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


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    requested_faculty_id = (data.get("faculty_id") or "uvt").strip()
    history = normalize_history(data.get("history"))

    if not question:
        return jsonify({
            "answer": "Intrebarea este goala.",
            "sources": [],
            "matched_faculty": FACULTY_MAP["uvt"]["name"],
            "confidence": "low",
            "confidence_score": 0,
            "confidence_reason": "Nu a fost primita nicio intrebare.",
            "live_verified": False,
        })

    faculty = infer_faculty(requested_faculty_id, question, history)
    faculty_id = faculty["id"]
    question_is_vague = is_vague_question(question)
    effective_question = build_effective_question(question, history)
    index_document = load_index()
    cache_key = build_cache_key(faculty_id, effective_question, history, index_document.get("built_at"))
    cached_response = get_cached_response(cache_key)
    if cached_response is not None:
        return jsonify(cached_response)

    retrieval_result = rank_index(effective_question, index_document, faculty_id, top_k=6)
    live_verified = False

    if retrieval_result.get("chunks"):
        merged_chunks, live_verified = live_verify_retrieval(
            effective_question,
            faculty_id,
            retrieval_result,
            index_document,
        )
        confidence = compute_confidence(merged_chunks[:4], retrieval_result.get("analysis"))
        retrieval_result["chunks"] = merged_chunks[:4]
        retrieval_result["confidence"] = confidence["label"]
        retrieval_result["confidence_score"] = confidence["score"]
        retrieval_result["confidence_reason"] = confidence["reason"]

    prompt = build_user_prompt(
        question,
        faculty["name"],
        retrieval_result,
        history=history,
        question_is_vague=question_is_vague,
    )

    try:
        llm_answer = ask_llm(SYSTEM_PROMPT, prompt)
    except Exception:
        llm_answer = build_local_fallback_answer(retrieval_result)

    response_payload = {
        "answer": llm_answer,
        "sources": unique_sources_from_chunks(retrieval_result.get("chunks", [])),
        "matched_faculty": faculty["name"],
        "matched_faculty_id": faculty_id,
        "confidence": retrieval_result.get("confidence", "low"),
        "confidence_score": retrieval_result.get("confidence_score", 0),
        "confidence_reason": retrieval_result.get("confidence_reason", ""),
        "live_verified": live_verified,
        "query_profile": {
            "intent": retrieval_result.get("analysis", {}).get("intent", "general"),
            "policy_question": retrieval_result.get("analysis", {}).get("is_policy_question", False),
            "normalized_question": retrieval_result.get("analysis", {}).get("corrected_question", question),
            "corrections": retrieval_result.get("analysis", {}).get("corrections", []),
        },
    }

    set_cached_response(cache_key, response_payload)
    return jsonify(response_payload)


@app.post("/feedback")
def feedback():
    data = request.get_json(silent=True) or {}
    append_feedback_record(data)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
