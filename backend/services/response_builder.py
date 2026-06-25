from __future__ import annotations

from page_index import normalize_url
from services.chat_models import FACULTY_MAP, GENERAL_FACULTY_ID
from services.chat_request_parser import compact_text


def numeric_confidence_score(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def append_confidence_reason(reason: str | None, suffix: str) -> str:
    reason = str(reason or "").strip()
    if suffix in reason:
        return reason
    return f"{reason} {suffix}".strip()


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
            "verified": False,
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

    return {
        "answerable": bool(chunks and confidence != "low"),
        "support_level": confidence,
        "source_count": len(unique_urls),
        "verified_source_count": 0,
        "live_verified": False,
        "top_source": {
            "title": compact_text(top_chunk.get("title"), 220),
            "url": top_chunk.get("url", ""),
            "page_type": top_chunk.get("page_type", "general"),
            "faculty_id": top_chunk.get("faculty_id", GENERAL_FACULTY_ID),
        } if top_chunk else None,
    }


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


def empty_response_payload() -> dict:
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
