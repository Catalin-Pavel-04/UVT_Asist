from __future__ import annotations

import copy
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from core.config import (
    CHAT_CACHE_VERSION,
    LIVE_VERIFY_ENABLED,
    LIVE_VERIFY_LIMIT,
    MAX_QUESTION_CHARS,
    RESPONSE_CACHE_TTL,
    env_int,
)
from faculties import FACULTIES
from ollama_client import ask_ollama_json
from page_index import build_chunk_entries_from_pages, get_index_status, load_index, metadata_index_document, normalize_url
from prompts import SYSTEM_PROMPT, build_answer_json_prompt, build_repair_prompt, build_user_prompt
from retriever import (
    compute_confidence,
    normalize as normalize_retrieval_text,
    rank_index,
    rank_lexical_index,
    rank_runtime_chunks,
)
from services.indexing_service import get_indexing_state, indexing_blocks_chat
from site_cache import verify_pages
from vector_store import get_vector_index_status

FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}
GENERAL_FACULTY_ID = "uvt"
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 500
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
    "am nevoie de ajutor administrativ ce sursa consult",
    "am o problema cu facultatea unde ma uit",
    "ce informatii sunt relevante pentru mine",
    "ce trebuie sa fac ca student",
    "ce trebuie sa stiu inainte de semestru",
    "ma poti ajuta cu facultatea",
    "spune-mi ceva util despre facultate",
    "unde gasesc informatiile importante",
    "unde gasesc tot ce imi trebuie",
}

UNSUPPORTED_QUESTION_PATTERNS = (
    r"\bmedia minima\b.*\banul viitor\b",
    r"\bsubiecte exacte\b.*\bmaine\b",
    r"\bce burs[ae]\b.*\bvoi primi\b",
    r"\bvoi primi\b.*\bburs[ae]\b",
    r"\bnota mea\b",
    r"\bprofesor va lipsi\b",
    r"\bdecizie va lua comisia\b",
    r"\bparola\b",
    r"\bvoi primi loc\b.*\bcamin\b",
    r"\btaxa exacta\b.*\bpeste doi ani\b",
    r"\bgarant[ae]?\b.*\bbuget\b",
)

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


def is_unsupported_question(question: str) -> bool:
    normalized_question = normalize_match_text(question)
    return any(re.search(pattern, normalized_question) for pattern in UNSUPPORTED_QUESTION_PATTERNS)


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
        timeout_seconds=env_int("OLLAMA_REQUEST_TIMEOUT_SECONDS", "120", minimum=15),
        num_predict=env_int("OLLAMA_NUM_PREDICT", "700", minimum=350),
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
    if faculty["id"] != GENERAL_FACULTY_ID or analysis.get("intent") not in FACULTY_SCOPED_INTENTS:
        return False

    normalized_question = normalize_retrieval_text(
        analysis.get("corrected_question") or analysis.get("normalized_question") or analysis.get("original_question") or ""
    )
    if analysis.get("intent") == "contact" and (
        "uvt" in normalized_question
        or "universitate" in normalized_question
        or "administrativ" in normalized_question
    ):
        return False

    return True


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


def unsupported_question_payload(chat_request: ChatRequest) -> dict:
    faculty = get_faculty(chat_request.requested_faculty_id)
    return {
        "answer": (
            "Sursele oficiale disponibile nu sunt suficiente pentru un raspuns sigur la aceasta intrebare. "
            "Nu pot confirma date personale, parole, note, decizii individuale sau predictii despre rezultate viitoare. "
            "Verifica portalurile oficiale sau contacteaza secretariatul/comisia relevanta."
        ),
        "sources": [],
        "matched_faculty": faculty["name"],
        "matched_faculty_id": faculty["id"],
        "confidence": "low",
        "confidence_score": 10,
        "confidence_reason": "Intrebarea cere date personale, garantii sau predictii care nu pot fi verificate din surse publice oficiale.",
        "live_verified": False,
        "query_profile": {
            "intent": "unsupported",
            "policy_question": False,
            "normalized_question": normalize_retrieval_text(chat_request.question),
            "corrections": [],
        },
        "retrieval_backend": "unsupported_guard",
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


def vague_question_payload(chat_request: ChatRequest) -> dict:
    faculty = get_faculty(chat_request.requested_faculty_id)
    return {
        "answer": (
            "Intrebarea este prea generala pentru un raspuns sigur din surse oficiale. "
            "Precizeaza tema, de exemplu orar, secretariat, admitere, burse, cazare, calendar academic "
            "sau credite de voluntariat."
        ),
        "sources": [],
        "matched_faculty": faculty["name"],
        "matched_faculty_id": faculty["id"],
        "confidence": "low",
        "confidence_score": 25,
        "confidence_reason": "Intrebarea nu contine suficiente indicii concrete pentru selectie sigura de surse.",
        "live_verified": False,
        "query_profile": {
            "intent": "clarification",
            "policy_question": False,
            "normalized_question": normalize_retrieval_text(chat_request.question),
            "corrections": [],
        },
        "retrieval_backend": "clarification",
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


SOURCE_NAVIGATION_PATTERNS = (
    "unde gasesc",
    "unde este",
    "unde sunt",
    "unde consult",
    "unde verific",
    "unde vad",
    "unde pot",
    "unde se publica",
    "care este pagina",
    "care este sursa",
    "ce sursa oficiala",
    "ce document oficial",
    "la ce pagina",
)


def is_source_navigation_question(question: str, retrieval_result: dict) -> bool:
    analysis = retrieval_result.get("analysis", {})
    normalized_question = normalize_retrieval_text(question)
    is_navigation = any(pattern in normalized_question for pattern in SOURCE_NAVIGATION_PATTERNS)
    if not analysis.get("is_policy_question"):
        return is_navigation
    return is_navigation and any(
        term in normalized_question
        for term in ("sursa", "document oficial", "metodolog", "regulament", "procedura")
    )


def should_use_source_navigation_answer(question: str, retrieval_result: dict) -> bool:
    chunks = retrieval_result.get("chunks") or []
    if not chunks:
        return False
    if retrieval_result.get("confidence") == "low":
        return False
    return is_source_navigation_question(question, retrieval_result)


def source_navigation_topic(question: str, retrieval_result: dict) -> str:
    normalized_question = normalize_retrieval_text(question)
    analysis = retrieval_result.get("analysis", {})
    if "secretariat" in normalized_question:
        return "secretariat/contact"
    if "contact" in normalized_question:
        return "contact"
    if ("cazare" in normalized_question or "camin" in normalized_question) and "social" in normalized_question:
        return "criteriile sociale pentru cazare"
    if "cazare" in normalized_question or "camin" in normalized_question:
        return "cazare"
    if any(
        term in normalized_question
        for term in ("calendar", "structura anului", "semestru", "sesiune", "vacanta", "vacante", "saptamani")
    ):
        return "calendarul academic"
    if "admitere" in normalized_question:
        return "admitere"
    if "burse" in normalized_question or "bursa" in normalized_question:
        return "burse"
    if "metodolog" in normalized_question:
        return "metodologia oficiala"
    if "document oficial" in normalized_question:
        return "documentul oficial"
    if "hotarar" in normalized_question and "regulament" in normalized_question:
        return "regulamentele si hotararile oficiale"
    if "regulament" in normalized_question or "procedura" in normalized_question:
        return "regulamentul sau procedura oficiala"
    if "voluntariat" in normalized_question or "credite" in normalized_question:
        return "credite de voluntariat"
    if analysis.get("intent") == "orar" or "orar" in normalized_question:
        return "orar"
    return "informatiile cerute"


def is_central_uvt_contact_request(question: str, faculty: dict, retrieval_result: dict) -> bool:
    if faculty["id"] != GENERAL_FACULTY_ID:
        return False
    analysis = retrieval_result.get("analysis", {})
    if analysis.get("intent") != "contact":
        return False
    normalized_question = normalize_retrieval_text(question)
    return (
        "uvt" in normalized_question
        or "universitate" in normalized_question
        or "administrativ" in normalized_question
    )


def find_canonical_uvt_contact_chunk() -> dict | None:
    for chunk in load_index().get("chunks", []):
        if str(chunk.get("url") or "").rstrip("/") == "https://uvt.ro/contact":
            return copy.deepcopy(chunk)
    return None


def ensure_canonical_uvt_contact_source(question: str, faculty: dict, retrieval_result: dict) -> dict:
    if not is_central_uvt_contact_request(question, faculty, retrieval_result):
        return retrieval_result

    chunks = list(retrieval_result.get("chunks") or [])
    if any(str(chunk.get("url") or "").rstrip("/") == "https://uvt.ro/contact" for chunk in chunks):
        return retrieval_result

    canonical_chunk = find_canonical_uvt_contact_chunk()
    if not canonical_chunk:
        return retrieval_result

    canonical_chunk["retrieval_score"] = max(float(canonical_chunk.get("retrieval_score", 0) or 0), 180.0)
    canonical_chunk["match_signals"] = list(dict.fromkeys([
        *canonical_chunk.get("match_signals", []),
        "canonical_contact",
        "contact_exact_path",
    ]))
    canonical_chunk["page_type"] = canonical_chunk.get("page_type") or "contact"

    filtered_chunks = [
        chunk for chunk in chunks
        if str(chunk.get("url") or "").rstrip("/") != "https://uvt.ro/contact"
    ]
    updated_result = {
        **retrieval_result,
        "chunks": [canonical_chunk, *filtered_chunks],
        "confidence_reason": append_confidence_reason(
            retrieval_result.get("confidence_reason"),
            "A fost prioritizata pagina oficiala centrala de contact UVT.",
        ),
    }
    confidence = compute_confidence(updated_result["chunks"], updated_result.get("analysis", {}))
    updated_result["confidence"] = confidence["label"]
    updated_result["confidence_score"] = confidence["score"]
    updated_result["confidence_reason"] = append_confidence_reason(
        updated_result.get("confidence_reason"),
        confidence["reason"],
    )
    return updated_result


def build_source_navigation_answer(question: str, retrieval_result: dict) -> str:
    sources = unique_sources_from_chunks(retrieval_result.get("chunks", []))
    if not sources:
        return build_local_fallback_answer(
            retrieval_result,
            reason="Nu exista o sursa oficiala suficient de clara pentru un raspuns direct.",
        )

    top = sources[0]
    title = compact_text(top.get("title") or "Sursa oficiala", 180)
    url = compact_text(top.get("url"), 500)
    topic = source_navigation_topic(question, retrieval_result)
    if len(sources) == 1:
        return f"Pentru {topic}, consulta sursa oficiala \"{title}\" - {url}."

    extra_sources = []
    for source in sources[1:3]:
        source_title = compact_text(source.get("title") or "Sursa oficiala", 120)
        source_url = compact_text(source.get("url"), 500)
        if source_url:
            extra_sources.append(f"\"{source_title}\" - {source_url}")

    if extra_sources:
        return (
            f"Pentru {topic}, consulta mai intai sursa oficiala \"{title}\" - {url}. "
            f"Surse oficiale suplimentare: {'; '.join(extra_sources)}."
        )
    return f"Pentru {topic}, consulta sursa oficiala \"{title}\" - {url}."


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




def handle_chat(payload) -> tuple[dict, int]:
    chat_request = parse_chat_request(payload)
    if not chat_request.question:
        return empty_question_payload(), 200
    if is_unsupported_question(chat_request.question):
        return unsupported_question_payload(chat_request), 200
    if indexing_blocks_chat():
        return indexing_in_progress_payload(chat_request), 503
    if is_vague_question(chat_request.question) and not chat_request.history:
        return vague_question_payload(chat_request), 200

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
        return cached_response, 200

    retrieval_result = rank_with_full_json_fallback(effective_question, index_document, faculty["id"], top_k=6)
    if needs_faculty_clarification(faculty, retrieval_result):
        response_payload = faculty_clarification_payload(faculty, retrieval_result)
        set_cached_response(cache_key, response_payload)
        return response_payload, 200

    retrieval_result = ensure_canonical_uvt_contact_source(chat_request.question, faculty, retrieval_result)

    live_verified = False

    if retrieval_result.get("chunks"):
        merged_chunks, live_verified = live_verify_retrieval(
            effective_question,
            faculty["id"],
            retrieval_result,
            index_document,
        )
        refresh_confidence(retrieval_result, merged_chunks)

    if should_use_source_navigation_answer(chat_request.question, retrieval_result):
        generation = {"mode": "local_source_navigation"}
        answer = build_source_navigation_answer(chat_request.question, retrieval_result)
    elif should_skip_generation(retrieval_result):
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
    return response_payload, 200
