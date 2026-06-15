from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS

from faculties import FACULTIES
from ollama_client import ask_ollama_json, get_ollama_status
from page_index import build_chunk_entries_from_pages, get_index_status, load_index, metadata_index_document, normalize_url
from prompts import SYSTEM_PROMPT, build_answer_json_prompt, build_repair_prompt, build_user_prompt
from retriever import (
    compute_confidence,
    normalize as normalize_retrieval_text,
    query_analysis_enabled,
    rank_index,
    rank_lexical_index,
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


def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


MAX_QUESTION_CHARS = max(120, int(os.getenv("MAX_QUESTION_CHARS", "1200")))
LIVE_VERIFY_ENABLED = env_bool("LIVE_VERIFY_ENABLED", "true")
LIVE_VERIFY_LIMIT = max(0, int(os.getenv("LIVE_VERIFY_LIMIT", "2")))
RESPONSE_CACHE_TTL = max(60, int(os.getenv("CHAT_RESPONSE_CACHE_TTL", "300")))
CHAT_CACHE_VERSION = os.getenv("CHAT_CACHE_VERSION", "2026-06-01-rag-v3").strip() or "2026-06-01-rag-v3"
MAX_FEEDBACK_TEXT_CHARS = max(200, int(os.getenv("MAX_FEEDBACK_TEXT_CHARS", "4000")))
MAX_FEEDBACK_SOURCES = max(1, int(os.getenv("MAX_FEEDBACK_SOURCES", "6")))
STARTUP_REBUILD_INDEX = env_bool("STARTUP_REBUILD_INDEX", "false")
STARTUP_REBUILD_FULL_SITE = env_bool("STARTUP_REBUILD_FULL_SITE", "true")
STARTUP_USE_SITEMAPS = env_bool("STARTUP_USE_SITEMAPS", "true")
STARTUP_SKIP_VECTOR_INDEX = env_bool("STARTUP_SKIP_VECTOR_INDEX", "false")
STARTUP_MAX_URLS_PER_FACULTY = max(0, int(os.getenv("STARTUP_MAX_URLS_PER_FACULTY", "0")))
STARTUP_MAX_DEPTH = max(0, int(os.getenv("STARTUP_MAX_DEPTH", "5")))
STARTUP_MAX_LINKS_PER_PAGE = max(10, int(os.getenv("STARTUP_MAX_LINKS_PER_PAGE", "150")))
STARTUP_FETCH_WORKERS = max(1, int(os.getenv("STARTUP_FETCH_WORKERS", "12")))
STARTUP_TERMINAL_PROGRESS = env_bool("STARTUP_TERMINAL_PROGRESS", "true")

LOG_FILE = Path(__file__).with_name("feedback_log.jsonl")
FEEDBACK_LOCK = threading.Lock()
RESPONSE_CACHE_LOCK = threading.Lock()
RESPONSE_CACHE: dict[str, dict] = {}
INDEXING_STATE_LOCK = threading.Lock()
INDEXING_STATE: dict = {
    "enabled": STARTUP_REBUILD_INDEX,
    "running": False,
    "ready": True,
    "phase": "idle",
    "message": "Indexarea de startup nu ruleaza.",
    "progress": 0,
    "started_at": None,
    "finished_at": None,
    "error": "",
    "current_faculty": "",
    "processed_faculties": 0,
    "total_faculties": len(FACULTIES),
    "discovered_urls": 0,
    "fetched_pages": 0,
    "page_count": 0,
    "chunk_count": 0,
    "embedded_chunks": 0,
    "total_chunks": 0,
    "error_count": 0,
}
TERMINAL_PROGRESS_LOCK = threading.Lock()
TERMINAL_PROGRESS_STATE = {
    "last_rendered_at": 0.0,
    "last_progress": -1,
    "last_phase": "",
    "line_length": 0,
}
TERMINAL_PROGRESS_WIDTH = 20
TERMINAL_PROGRESS_MIN_INTERVAL = 0.35

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

FACULTY_SCOPED_INTENTS = {"orar", "contact"}
LIVE_VERIFY_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt"}

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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def set_indexing_state(**updates) -> dict:
    with INDEXING_STATE_LOCK:
        INDEXING_STATE.update(updates)
        return copy.deepcopy(INDEXING_STATE)


def get_indexing_state() -> dict:
    with INDEXING_STATE_LOCK:
        return copy.deepcopy(INDEXING_STATE)


def indexing_blocks_chat() -> bool:
    return bool(get_indexing_state().get("running"))


@app.get("/health")
def health():
    ollama_status = get_ollama_status()
    index_status = get_index_status()
    vector_status = get_vector_index_status()
    indexing_status = get_indexing_state()
    status_reasons: list[str] = []

    if indexing_status.get("running"):
        status_reasons.append("Startup index rebuild is still running.")
    elif indexing_status.get("error"):
        status_reasons.append(f"Startup index rebuild failed: {indexing_status['error']}")

    if not ollama_status.get("available"):
        status_reasons.append("Ollama is unavailable.")
    else:
        if not ollama_status.get("generation_model_available"):
            status_reasons.append("Configured Ollama generation model is not installed.")
        if not ollama_status.get("embedding_model_available"):
            status_reasons.append("Configured Ollama embedding model is not installed.")
    if not index_status.get("exists") or not index_status.get("chunk_count"):
        status_reasons.append("JSON index is missing or empty.")
    if not vector_status.get("available") or not vector_status.get("points_count"):
        status_reasons.append("Qdrant vector index is unavailable or empty.")
    elif index_status.get("chunk_count") and vector_status.get("points_count") != index_status.get("chunk_count"):
        status_reasons.append("Qdrant point count does not match the JSON index chunk count.")

    status = "ok" if not status_reasons else "degraded"
    vector_ready = bool(
        ollama_status.get("available")
        and ollama_status.get("embedding_model_available")
        and vector_status.get("available")
        and vector_status.get("points_count")
    )
    retrieval_mode = "qdrant-vector-rag" if vector_ready else "local-json-lexical-fallback"

    return jsonify({
        "status": status,
        "status_reasons": status_reasons,
        "ready": status == "ok" and not indexing_status.get("running"),
        "checks": {
            "ollama": bool(ollama_status.get("available")),
            "generation_model": bool(ollama_status.get("generation_model_available")),
            "embedding_model": bool(ollama_status.get("embedding_model_available")),
            "json_index": bool(index_status.get("exists") and index_status.get("chunk_count")),
            "qdrant_index": bool(vector_status.get("available") and vector_status.get("points_count")),
            "index_vector_count_match": bool(
                index_status.get("chunk_count")
                and vector_status.get("points_count") == index_status.get("chunk_count")
            ),
        },
        "llm_provider": "ollama",
        "embedding_provider": "ollama",
        "ollama_query_analysis_enabled": query_analysis_enabled(),
        "retrieval_mode": retrieval_mode,
        "live_verification_enabled": bool(LIVE_VERIFY_ENABLED and LIVE_VERIFY_LIMIT > 0),
        "live_verify_limit": LIVE_VERIFY_LIMIT,
        "chat_cache_version": CHAT_CACHE_VERSION,
        "startup_indexing": {
            "enabled": STARTUP_REBUILD_INDEX,
            "full_site": STARTUP_REBUILD_FULL_SITE,
            "use_sitemaps": STARTUP_USE_SITEMAPS,
            "skip_vector_index": STARTUP_SKIP_VECTOR_INDEX,
            "max_urls_per_faculty": STARTUP_MAX_URLS_PER_FACULTY,
            "max_depth": STARTUP_MAX_DEPTH,
            "max_links_per_page": STARTUP_MAX_LINKS_PER_PAGE,
            "fetch_workers": STARTUP_FETCH_WORKERS,
            "terminal_progress": STARTUP_TERMINAL_PROGRESS,
        },
        "indexing": indexing_status,
        "ollama": ollama_status,
        "index": index_status,
        "vector_index": vector_status,
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


@app.get("/indexing/status")
def indexing_status():
    return jsonify({"indexing": get_indexing_state()})


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


def normalize_payload(payload) -> dict:
    return payload if isinstance(payload, dict) else {}


def compact_text(value, max_chars: int) -> str:
    return " ".join(str(value or "").split()).strip()[:max_chars]


def parse_chat_request(payload) -> ChatRequest:
    payload = normalize_payload(payload)
    return ChatRequest(
        question=compact_text(payload.get("question"), MAX_QUESTION_CHARS),
        requested_faculty_id=compact_text(payload.get("faculty_id") or GENERAL_FACULTY_ID, 64),
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

        content = compact_text(item.get("content"), MAX_HISTORY_CHARS)
        if content:
            normalized_history.append({"role": role, "content": content})

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
        "chat_cache_version": CHAT_CACHE_VERSION,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def get_cached_response(cache_key: str) -> dict | None:
    now = time.time()
    with RESPONSE_CACHE_LOCK:
        cached = RESPONSE_CACHE.get(cache_key)
        if cached and now - cached["timestamp"] < RESPONSE_CACHE_TTL:
            return copy.deepcopy(cached["response"])
    return None


def set_cached_response(cache_key: str, response_payload: dict) -> None:
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = {"timestamp": time.time(), "response": copy.deepcopy(response_payload)}


def merge_ranked_chunks(primary_chunks: list[dict], verified_chunks: list[dict]) -> list[dict]:
    verified_by_url: dict[str, list[dict]] = {}
    for chunk in verified_chunks:
        normalized_url = normalize_url(chunk.get("url", ""))
        if not normalized_url:
            continue
        verified_by_url.setdefault(normalized_url, []).append(dict(chunk))

    for chunks in verified_by_url.values():
        chunks.sort(key=lambda item: item.get("retrieval_score", 0), reverse=True)

    merged: list[dict] = []
    used_verified_chunk_ids: set[str] = set()
    verified_offsets: dict[str, int] = {}
    primary_urls: set[str] = set()
    for primary_chunk in primary_chunks:
        normalized_url = normalize_url(primary_chunk.get("url", ""))
        if not normalized_url:
            continue

        merged_chunk = dict(primary_chunk)
        primary_urls.add(normalized_url)
        verified_candidates = verified_by_url.get(normalized_url, [])
        offset = verified_offsets.get(normalized_url, 0)
        verified_chunk = verified_candidates[offset] if offset < len(verified_candidates) else None
        if verified_chunk:
            merged_chunk["title"] = verified_chunk.get("title") or merged_chunk.get("title")
            merged_chunk["chunk_text"] = verified_chunk.get("chunk_text") or merged_chunk.get("chunk_text")
            merged_chunk["verified"] = True
            verified_offsets[normalized_url] = offset + 1
            if verified_chunk.get("chunk_id"):
                used_verified_chunk_ids.add(str(verified_chunk["chunk_id"]))
        merged.append(merged_chunk)

    remaining_verified_chunks = [
        chunk
        for chunks in verified_by_url.values()
        for chunk in chunks
        if str(chunk.get("chunk_id") or "") not in used_verified_chunk_ids
    ]
    for verified_chunk in sorted(remaining_verified_chunks, key=lambda item: item.get("retrieval_score", 0), reverse=True):
        normalized_url = normalize_url(verified_chunk.get("url", ""))
        if normalized_url and normalized_url not in primary_urls:
            merged.append(verified_chunk)
            primary_urls.add(normalized_url)

    return merged


def unique_sources_from_chunks(chunks: list[dict]) -> list[dict]:
    seen: set[str] = set()
    sources: list[dict] = []

    for chunk in chunks:
        url = str(chunk.get("url", "")).strip()
        normalized_url = normalize_url(url)
        if not url or not normalized_url or normalized_url in seen:
            continue

        sources.append({
            "title": compact_text(chunk.get("title") or url, 220),
            "url": url,
            "faculty_id": chunk.get("faculty_id", GENERAL_FACULTY_ID),
            "page_type": chunk.get("page_type", "general"),
            "verified": bool(chunk.get("verified")),
        })
        seen.add(normalized_url)

    return sources


def source_reference(title: str, url: str) -> str:
    safe_title = compact_text(title or "sursa oficiala", 220)
    safe_url = compact_text(url, 500)
    if safe_url:
        return f"\"{safe_title}\" - {safe_url}"
    return f"\"{safe_title}\""


def build_source_summary_answer(retrieval_result: dict, reason: str | None = None) -> str:
    chunks = retrieval_result.get("chunks", [])
    sources = unique_sources_from_chunks(chunks)[:2]
    if not sources:
        return (
            "Nu exista suficiente fragmente oficiale selectate de backend pentru a trimite un context util catre Ollama. "
            "Nu pot formula un raspuns sigur si nu pot cita o sursa specifica pentru aceasta intrebare."
        )

    source_list = "; ".join(source_reference(source["title"], source["url"]) for source in sources)
    prefix = reason or "Nu pot genera local un raspuns de continut, deoarece analiza informatiei este rezervata pentru Ollama."
    if retrieval_result.get("confidence") == "low":
        return (
            f"{prefix} Backend-ul a gasit doar dovezi partiale sau prea generale. "
            f"Sursele oficiale cele mai apropiate sunt: {source_list}."
        )

    return (
        f"{prefix} Backend-ul a selectat urmatoarele surse oficiale pentru intrebare: {source_list}."
    )


def build_local_fallback_answer(retrieval_result: dict, reason: str | None = None) -> str:
    return build_source_summary_answer(retrieval_result, reason=reason)


def build_evidence_profile(retrieval_result: dict, live_verified: bool) -> dict:
    chunks = retrieval_result.get("chunks", [])
    confidence = retrieval_result.get("confidence", "low")
    top_chunk = chunks[0] if chunks else {}
    unique_urls = {normalize_url(chunk.get("url", "")) for chunk in chunks if chunk.get("url")}
    verified_urls = {
        normalize_url(chunk.get("url", ""))
        for chunk in chunks
        if chunk.get("url") and chunk.get("verified")
    }

    return {
        "answerable": bool(chunks and confidence != "low"),
        "support_level": confidence,
        "source_count": len(unique_urls),
        "verified_source_count": len(verified_urls),
        "live_verified": bool(live_verified),
        "top_source": {
            "title": compact_text(top_chunk.get("title"), 220),
            "url": top_chunk.get("url", ""),
            "page_type": top_chunk.get("page_type", "general"),
            "faculty_id": top_chunk.get("faculty_id", GENERAL_FACULTY_ID),
        } if top_chunk else None,
    }


def answer_needs_fallback(answer: str) -> bool:
    head = " ".join(str(answer).split()).lower()[:900]
    if not head:
        return True
    return any(marker in head for marker in BAD_GENERATION_MARKERS)


def ask_ollama_answer(answer_prompt: str) -> str:
    response = ask_ollama_json(
        SYSTEM_PROMPT,
        build_answer_json_prompt(answer_prompt),
        timeout_seconds=max(15, int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "120"))),
        num_predict=max(350, int(os.getenv("OLLAMA_NUM_PREDICT", "700"))),
    )
    answer = str(response.get("answer") or "").strip()
    if not answer:
        raise RuntimeError("Ollama did not return an answer field.")
    return answer


def repair_generated_answer(prompt: str, flawed_answer: str) -> str | None:
    repaired_answer = ask_ollama_answer(build_repair_prompt(prompt, flawed_answer))
    if answer_needs_fallback(repaired_answer):
        return None
    return repaired_answer


def live_verify_retrieval(
    effective_question: str,
    faculty_id: str,
    retrieval_result: dict,
    index_document: dict,
) -> tuple[list[dict], bool]:
    if not LIVE_VERIFY_ENABLED or LIVE_VERIFY_LIMIT <= 0:
        return retrieval_result.get("chunks", []), False

    top_urls = [chunk.get("url") for chunk in retrieval_result.get("chunks", []) if chunk.get("url")]
    deep_document_verify = should_deep_verify_documents(retrieval_result)
    verified_pages = verify_pages(top_urls, max_pages=LIVE_VERIFY_LIMIT, index_mode=deep_document_verify)
    if not verified_pages:
        return retrieval_result.get("chunks", []), False

    verified_chunks = build_chunk_entries_from_pages(verified_pages, FACULTIES)
    verified_result = rank_runtime_chunks(
        verified_chunks,
        effective_question,
        faculty_id,
        idf={},
        top_k=4,
    )
    verified_urls = {normalize_url(page.get("url", "")) for page in verified_pages if page.get("url")}
    merged_chunks = merge_ranked_chunks(retrieval_result.get("chunks", []), verified_result.get("chunks", []))

    for chunk in merged_chunks:
        if normalize_url(chunk.get("url", "")) in verified_urls:
            chunk["verified"] = True

    return merged_chunks[:6], True


def is_document_source_url(url: str) -> bool:
    return Path(urlparse(str(url)).path.lower()).suffix in LIVE_VERIFY_DOCUMENT_EXTENSIONS


def should_deep_verify_documents(retrieval_result: dict) -> bool:
    analysis = retrieval_result.get("analysis", {})
    if not analysis.get("is_policy_question"):
        return False
    return any(is_document_source_url(chunk.get("url", "")) for chunk in retrieval_result.get("chunks", []))


def refresh_confidence(retrieval_result: dict, chunks: list[dict]) -> None:
    confidence = compute_confidence(chunks[:4], retrieval_result.get("analysis"))
    retrieval_result["chunks"] = chunks[:4]
    retrieval_result["confidence"] = confidence["label"]
    retrieval_result["confidence_score"] = confidence["score"]
    retrieval_result["confidence_reason"] = confidence["reason"]


def build_response_payload(
    answer: str,
    faculty: dict,
    retrieval_result: dict,
    live_verified: bool,
    generation: dict | None = None,
) -> dict:
    analysis = retrieval_result.get("analysis", {})
    generation = generation or {"mode": "unknown"}
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
        "generation_mode": generation.get("mode", "unknown"),
        "generation_error": generation.get("error", ""),
        "evidence": build_evidence_profile(retrieval_result, live_verified),
    }


def needs_faculty_clarification(faculty: dict, retrieval_result: dict) -> bool:
    analysis = retrieval_result.get("analysis", {})
    return faculty["id"] == GENERAL_FACULTY_ID and analysis.get("intent") in FACULTY_SCOPED_INTENTS


def faculty_clarification_payload(faculty: dict, retrieval_result: dict) -> dict:
    intent = retrieval_result.get("analysis", {}).get("intent", "general")
    label = "orarul" if intent == "orar" else "secretariatul/contactul"
    retrieval_result = {
        **retrieval_result,
        "chunks": [],
        "confidence": "low",
        "confidence_score": 20,
        "confidence_reason": "Intrebarea necesita alegerea unei facultati concrete.",
        "retrieval_backend": "clarification",
    }
    answer = (
        f"Pentru {label}, alege mai intai facultatea din lista sau mentioneaza numele ei in intrebare. "
        "Fara facultate, exista mai multe pagini oficiale posibile si nu pot alege sigur una singura."
    )
    return build_response_payload(answer, faculty, retrieval_result, False, {"mode": "clarification"})


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
        "generation_mode": "none",
        "generation_error": "",
        "evidence": {
            "answerable": False,
            "support_level": "low",
            "source_count": 0,
            "verified_source_count": 0,
            "live_verified": False,
            "top_source": None,
        },
    }


def indexing_in_progress_payload(chat_request: ChatRequest) -> dict:
    faculty = get_faculty(chat_request.requested_faculty_id)
    indexing_status = get_indexing_state()
    progress = numeric_confidence_score(indexing_status.get("progress"))
    message = indexing_status.get("message") or "Indexarea surselor oficiale este in curs."

    return {
        "answer": (
            "Indexarea surselor oficiale UVT este in curs. "
            f"Progres curent: {progress}%. {message} "
            "Raspunsurile vor fi disponibile dupa finalizarea indexarii."
        ),
        "sources": [],
        "matched_faculty": faculty["name"],
        "matched_faculty_id": faculty["id"],
        "confidence": "low",
        "confidence_score": 0,
        "confidence_reason": "Indexarea de startup nu s-a finalizat inca.",
        "live_verified": False,
        "query_profile": {
            "intent": "indexing",
            "policy_question": False,
            "normalized_question": "",
            "corrections": [],
        },
        "retrieval_backend": "indexing",
        "generation_mode": "none",
        "generation_error": "",
        "indexing": indexing_status,
        "evidence": {
            "answerable": False,
            "support_level": "low",
            "source_count": 0,
            "verified_source_count": 0,
            "live_verified": False,
            "top_source": None,
        },
    }


def numeric_confidence_score(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def should_skip_generation(retrieval_result: dict) -> bool:
    return not retrieval_result.get("chunks")


def vector_runtime_ready(vector_status: dict) -> bool:
    return bool(vector_status.get("available") and vector_status.get("points_count"))


def load_runtime_index_document(vector_status: dict) -> dict:
    if vector_runtime_ready(vector_status):
        return metadata_index_document(get_index_status())
    return load_index()


def is_metadata_only_index_document(index_document: dict) -> bool:
    try:
        chunk_count = int(index_document.get("chunk_count") or 0)
    except (TypeError, ValueError):
        chunk_count = 0
    return chunk_count > 0 and not index_document.get("chunks")


def append_confidence_reason(reason: str | None, suffix: str) -> str:
    reason = str(reason or "").strip()
    if suffix in reason:
        return reason
    return f"{reason} {suffix}".strip()


def should_retry_full_json_fallback(retrieval_result: dict, index_document: dict) -> bool:
    return not retrieval_result.get("chunks") and is_metadata_only_index_document(index_document)


def rank_with_full_json_fallback(
    question: str,
    index_document: dict,
    selected_faculty: str,
    top_k: int = 6,
) -> dict:
    retrieval_result = rank_index(question, index_document, selected_faculty, top_k=top_k)
    if not should_retry_full_json_fallback(retrieval_result, index_document):
        return retrieval_result

    vector_error = retrieval_result.get("vector_error")
    try:
        full_index_document = load_index()
        if not full_index_document.get("chunks"):
            return retrieval_result
        fallback_result = rank_lexical_index(question, full_index_document, selected_faculty, top_k=top_k)
    except Exception as exc:
        retrieval_result["fallback_error"] = compact_text(exc, 800)
        retrieval_result["confidence_reason"] = append_confidence_reason(
            retrieval_result.get("confidence_reason"),
            "Fallback-ul lexical complet nu a putut incarca indexul JSON.",
        )
        return retrieval_result

    fallback_result["retrieval_backend"] = "local_json_fallback"
    if vector_error:
        fallback_result["vector_error"] = vector_error
    fallback_result["confidence_reason"] = append_confidence_reason(
        fallback_result.get("confidence_reason"),
        "Fallback lexical folosit dupa ce cautarea vectoriala nu a returnat fragmente utilizabile.",
    )
    return fallback_result


@app.post("/chat")
def chat():
    chat_request = parse_chat_request(request.get_json(silent=True) or {})
    if not chat_request.question:
        return jsonify(empty_question_payload())
    if indexing_blocks_chat():
        return jsonify(indexing_in_progress_payload(chat_request)), 503

    faculty = infer_faculty(chat_request.requested_faculty_id, chat_request.question, chat_request.history)
    effective_question = build_effective_question(chat_request.question, chat_request.history)
    question_is_vague = is_vague_question(chat_request.question)
    vector_status = get_vector_index_status()
    index_document = load_runtime_index_document(vector_status)

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

    retrieval_result = rank_with_full_json_fallback(effective_question, index_document, faculty["id"], top_k=6)
    if needs_faculty_clarification(faculty, retrieval_result):
        response_payload = faculty_clarification_payload(faculty, retrieval_result)
        set_cached_response(cache_key, response_payload)
        return jsonify(response_payload)

    live_verified = False

    if retrieval_result.get("chunks"):
        merged_chunks, live_verified = live_verify_retrieval(
            effective_question,
            faculty["id"],
            retrieval_result,
            index_document,
        )
        refresh_confidence(retrieval_result, merged_chunks)

    if should_skip_generation(retrieval_result):
        generation = {"mode": "fallback_low_evidence"}
        answer = build_local_fallback_answer(
            retrieval_result,
            reason="Nu exista context oficial selectat pentru generarea cu Ollama.",
        )
    else:
        prompt = build_user_prompt(
            chat_request.question,
            faculty["name"],
            retrieval_result,
            history=chat_request.history,
            question_is_vague=question_is_vague,
        )
        generation = {"mode": "ollama"}
        try:
            answer = ask_ollama_answer(prompt)
            if answer_needs_fallback(answer):
                repaired_answer = repair_generated_answer(prompt, answer)
                if repaired_answer:
                    generation = {"mode": "ollama_repair"}
                    answer = repaired_answer
                else:
                    generation = {"mode": "fallback_bad_generation"}
                    answer = build_local_fallback_answer(
                        retrieval_result,
                        reason="Raspunsul generat de Ollama nu a respectat contractul de siguranta.",
                    )
        except Exception as exc:
            generation = {"mode": "fallback_ollama_error", "error": compact_text(exc, 800)}
            answer = build_local_fallback_answer(
                retrieval_result,
                reason="Ollama nu a putut genera raspunsul in acest moment.",
            )

    response_payload = build_response_payload(answer, faculty, retrieval_result, live_verified, generation)
    set_cached_response(cache_key, response_payload)
    return jsonify(response_payload)


def append_feedback_record(payload: dict) -> None:
    payload = normalize_payload(payload)
    sources = unique_sources_from_chunks(payload.get("sources", []))[:MAX_FEEDBACK_SOURCES]
    record = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "question": compact_text(payload.get("question"), MAX_FEEDBACK_TEXT_CHARS),
        "selected_faculty": compact_text(payload.get("faculty_id"), 64),
        "matched_faculty": compact_text(payload.get("matched_faculty"), 220),
        "answer": compact_text(payload.get("answer"), MAX_FEEDBACK_TEXT_CHARS),
        "confidence": compact_text(payload.get("confidence"), 32),
        "confidence_score": payload.get("confidence_score"),
        "feedback_vote": compact_text(payload.get("feedback"), 32),
        "sources": sources,
        "source": compact_text(payload.get("source") or "popup", 64),
        "live_verified": bool(payload.get("live_verified")),
        "retrieval_backend": compact_text(payload.get("retrieval_backend"), 64),
        "generation_mode": compact_text(payload.get("generation_mode"), 64),
        "generation_error": compact_text(payload.get("generation_error"), 800),
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


def should_run_startup_index_rebuild(debug: bool) -> bool:
    if not STARTUP_REBUILD_INDEX:
        return False
    if debug and os.getenv("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def describe_indexing_progress(update: dict) -> str:
    phase = update.get("phase") or "indexing"
    faculty_name = update.get("current_faculty") or ""

    if phase == "discovering":
        message = "Descopar paginile oficiale UVT."
    elif phase == "fetching":
        message = "Descarc si extrag continutul din paginile oficiale."
    elif phase == "chunking":
        message = "Transform paginile in fragmente pentru cautare."
    elif phase == "embedding":
        done = int(update.get("embedded_chunks") or 0)
        total = int(update.get("total_chunks") or update.get("chunk_count") or 0)
        message = f"Generez embeddings local cu Ollama ({done}/{total} fragmente)."
    elif phase == "saving":
        message = "Salvez indexul JSON si vectorii in Qdrant."
    elif phase == "ready":
        message = "Indexarea s-a finalizat."
    else:
        message = "Indexarea este in curs."

    if faculty_name and phase in {"discovering", "fetching"}:
        message = f"{message} Sectiune curenta: {faculty_name}."
    return message


def terminal_progress_enabled() -> bool:
    return bool(STARTUP_TERMINAL_PROGRESS)


def terminal_text(value, max_chars: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars - 3]}..."


def compact_exception(exc: Exception, max_chars: int) -> str:
    message = compact_text(exc, max_chars)
    exception_type = type(exc).__name__
    if not message:
        return exception_type
    return compact_text(f"{exception_type}: {message}", max_chars)


def build_terminal_progress_suffix(state: dict) -> str:
    phase = state.get("phase")
    if phase in {"discovering", "fetching"}:
        parts = [
            f"facultati {int(state.get('processed_faculties') or 0)}/{int(state.get('total_faculties') or len(FACULTIES))}",
            f"url-uri {int(state.get('discovered_urls') or 0)}",
            f"pagini {int(state.get('fetched_pages') or 0)}",
        ]
        errors = int(state.get("error_count") or 0)
        if errors:
            parts.append(f"erori {errors}")
        return ", ".join(parts)

    if phase == "embedding":
        done = int(state.get("embedded_chunks") or 0)
        total = int(state.get("total_chunks") or state.get("chunk_count") or 0)
        return f"embeddings {done}/{total}"

    if phase in {"chunking", "saving", "ready"}:
        pages = int(state.get("page_count") or 0)
        chunks = int(state.get("chunk_count") or 0)
        errors = int(state.get("error_count") or 0)
        suffix = f"pagini {pages}, fragmente {chunks}"
        return f"{suffix}, erori {errors}" if errors else suffix

    return ""


def render_terminal_indexing_progress(state: dict, force: bool = False, final: bool = False) -> None:
    if not terminal_progress_enabled():
        return

    progress = max(0, min(100, int(state.get("progress", 0) or 0)))
    phase = terminal_text(state.get("phase") or "indexing", 14)
    message = terminal_text(state.get("message") or "Indexarea este in curs.", 48)
    suffix = terminal_text(build_terminal_progress_suffix(state), 38)
    now = time.time()

    with TERMINAL_PROGRESS_LOCK:
        should_render = (
            force
            or final
            or progress != TERMINAL_PROGRESS_STATE["last_progress"]
            or phase != TERMINAL_PROGRESS_STATE["last_phase"]
            or now - TERMINAL_PROGRESS_STATE["last_rendered_at"] >= TERMINAL_PROGRESS_MIN_INTERVAL
        )
        if not should_render:
            return

        filled = int(TERMINAL_PROGRESS_WIDTH * progress / 100)
        bar = "#" * filled + "-" * (TERMINAL_PROGRESS_WIDTH - filled)
        line = f"Indexare UVT [{bar}] {progress:3d}% {phase} | {message}"
        if suffix:
            line = f"{line} | {suffix}"
        terminal_width = shutil.get_terminal_size(fallback=(100, 20)).columns
        line = terminal_text(line, max(72, terminal_width - 1))

        previous_length = int(TERMINAL_PROGRESS_STATE["line_length"] or 0)
        padding = " " * max(0, previous_length - len(line))
        dynamic_terminal = bool(getattr(sys.stdout, "isatty", lambda: False)())
        prefix = "\r" if dynamic_terminal else ""
        end = "\n" if final or not dynamic_terminal else ""
        print(f"{prefix}{line}{padding}", end=end, flush=True)

        TERMINAL_PROGRESS_STATE.update({
            "last_rendered_at": now,
            "last_progress": progress,
            "last_phase": phase,
            "line_length": 0 if final or not dynamic_terminal else len(line),
        })


def update_startup_index_progress(update: dict) -> None:
    state_update = {
        "phase": update.get("phase", "indexing"),
        "message": describe_indexing_progress(update),
        "progress": max(0, min(100, int(update.get("progress", 0) or 0))),
        "current_faculty": update.get("current_faculty", ""),
    }

    for key in (
        "processed_faculties",
        "total_faculties",
        "discovered_urls",
        "fetched_pages",
        "page_count",
        "chunk_count",
        "embedded_chunks",
        "total_chunks",
        "error_count",
    ):
        if key in update:
            state_update[key] = update[key]

    state = set_indexing_state(**state_update)
    render_terminal_indexing_progress(state)


def run_startup_index_rebuild() -> None:
    from build_index import build_index

    initial_state = set_indexing_state(
        enabled=True,
        running=True,
        ready=False,
        phase="starting",
        message="Pornesc indexarea completa a surselor oficiale UVT.",
        progress=1,
        started_at=utc_now_iso(),
        finished_at=None,
        error="",
        current_faculty="",
        processed_faculties=0,
        total_faculties=len(FACULTIES),
        discovered_urls=0,
        fetched_pages=0,
        page_count=0,
        chunk_count=0,
        embedded_chunks=0,
        total_chunks=0,
        error_count=0,
    )

    max_urls_per_faculty = STARTUP_MAX_URLS_PER_FACULTY
    max_depth = STARTUP_MAX_DEPTH
    max_links_per_page = STARTUP_MAX_LINKS_PER_PAGE
    fetch_workers = STARTUP_FETCH_WORKERS

    if STARTUP_REBUILD_FULL_SITE:
        if max_urls_per_faculty > 0:
            max_urls_per_faculty = max(max_urls_per_faculty, 800)
        max_depth = max(max_depth, 5)
        max_links_per_page = max(max_links_per_page, 150)
        fetch_workers = max(fetch_workers, 12)

    print(
        "Startup index rebuild enabled. "
        f"full_site={STARTUP_REBUILD_FULL_SITE}, sitemaps={STARTUP_USE_SITEMAPS}, "
        f"max_urls_per_faculty={max_urls_per_faculty}, max_depth={max_depth}, "
        f"max_links_per_page={max_links_per_page}, fetch_workers={fetch_workers}, "
        f"skip_vector_index={STARTUP_SKIP_VECTOR_INDEX}",
        flush=True,
    )
    render_terminal_indexing_progress(initial_state, force=True)
    started_at = time.time()
    try:
        document = build_index(
            max_urls_per_faculty=max_urls_per_faculty,
            max_depth=max_depth,
            max_links_per_page=max_links_per_page,
            fetch_workers=fetch_workers,
            use_sitemaps=STARTUP_USE_SITEMAPS,
            skip_vector_index=STARTUP_SKIP_VECTOR_INDEX,
            progress=update_startup_index_progress,
        )
        elapsed = time.time() - started_at
        final_state = set_indexing_state(
            running=False,
            ready=True,
            phase="ready",
            message="Indexarea completa s-a finalizat.",
            progress=100,
            finished_at=utc_now_iso(),
            error="",
            page_count=document.get("page_count", 0),
            chunk_count=document.get("chunk_count", 0),
        )
        render_terminal_indexing_progress(final_state, force=True, final=True)
        print(
            "Startup index rebuild finished. "
            f"pages={document.get('page_count', 0)}, chunks={document.get('chunk_count', 0)}, "
            f"elapsed_seconds={elapsed:.1f}",
            flush=True,
        )
    except Exception as exc:
        error_state = set_indexing_state(
            running=False,
            ready=False,
            phase="error",
            message="Indexarea de startup a esuat. Verifica serviciile locale si logurile backend.",
            finished_at=utc_now_iso(),
            error=compact_exception(exc, 900),
        )
        render_terminal_indexing_progress(error_state, force=True, final=True)
        print("Startup index rebuild failed with traceback:", flush=True)
        print(traceback.format_exc(), flush=True)


def start_startup_index_rebuild(debug: bool) -> None:
    if not should_run_startup_index_rebuild(debug):
        set_indexing_state(enabled=STARTUP_REBUILD_INDEX, running=False, ready=True)
        return

    thread = threading.Thread(target=run_startup_index_rebuild, name="startup-index-rebuild", daemon=True)
    thread.start()


if __name__ == "__main__":
    debug = flask_debug_enabled()
    start_startup_index_rebuild(debug)
    app.run(host="127.0.0.1", port=5000, debug=debug, use_reloader=debug)
