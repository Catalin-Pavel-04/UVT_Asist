from __future__ import annotations

import copy

from page_index import load_index, normalize_url
from rag.confidence import compute_confidence
from rag.text_normalization import normalize as normalize_retrieval_text
from services.chat_models import GENERAL_FACULTY_ID
from services.chat_request_parser import compact_text
from services.response_builder import (
    append_confidence_reason,
    build_local_fallback_answer,
    unique_sources_from_chunks,
)

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


def find_canonical_uvt_contact_chunk(load_index_func=load_index) -> dict | None:
    for chunk in load_index_func().get("chunks", []):
        if str(chunk.get("url") or "").rstrip("/") == "https://uvt.ro/contact":
            return copy.deepcopy(chunk)
    return None


def ensure_canonical_uvt_contact_source(
    question: str,
    faculty: dict,
    retrieval_result: dict,
    load_index_func=load_index,
) -> dict:
    if not is_central_uvt_contact_request(question, faculty, retrieval_result):
        return retrieval_result

    chunks = list(retrieval_result.get("chunks") or [])
    if any(str(chunk.get("url") or "").rstrip("/") == "https://uvt.ro/contact" for chunk in chunks):
        return retrieval_result

    canonical_chunk = find_canonical_uvt_contact_chunk(load_index_func=load_index_func)
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
            reason="Nu am gasit o sursa oficiala suficient de clara pentru un raspuns direct.",
        )

    top = sources[0]
    title = compact_text(top.get("title") or "Sursa oficiala", 180)
    url = compact_text(top.get("url"), 500)
    topic = source_navigation_topic(question, retrieval_result)
    if len(sources) == 1:
        return f"Pentru {topic}, cel mai bun punct de plecare este \"{title}\" - {url}."

    extra_sources = []
    for source in sources[1:3]:
        source_title = compact_text(source.get("title") or "Sursa oficiala", 120)
        source_url = compact_text(source.get("url"), 500)
        if source_url:
            extra_sources.append(f"\"{source_title}\" - {source_url}")

    if extra_sources:
        return (
            f"Pentru {topic}, incepe cu sursa oficiala \"{title}\" - {url}. "
            f"Mai pot fi utile si: {'; '.join(extra_sources)}."
        )
    return f"Pentru {topic}, cel mai bun punct de plecare este \"{title}\" - {url}."
