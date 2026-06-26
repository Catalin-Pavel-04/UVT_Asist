from __future__ import annotations

import re

from rag.text_normalization import normalize as normalize_retrieval_text
from services.chat_models import GENERAL_FACULTY_ID, ChatRequest, get_faculty
from services.chat_request_parser import normalize_match_text
from services.indexing_service import get_indexing_state
from services.response_builder import empty_response_payload, numeric_confidence_score

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


def empty_question_payload() -> dict:
    return empty_response_payload()


def unsupported_question_payload(chat_request: ChatRequest) -> dict:
    faculty = get_faculty(chat_request.requested_faculty_id)
    return {
        "answer": (
            "Nu pot confirma asta din sursele oficiale indexate. "
            "Intrebarea cere date personale, parole, note, decizii individuale sau predictii despre rezultate viitoare. "
            "Pentru astfel de cazuri, verifica portalurile oficiale sau contacteaza secretariatul ori comisia relevanta."
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
            "Am nevoie de un pic mai mult context ca sa aleg sursa oficiala potrivita. "
            "Spune tema concreta: orar, secretariat, admitere, burse, cazare, calendar academic "
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


def query_analysis_clarification_payload(chat_request: ChatRequest, analysis) -> dict:
    faculty = get_faculty(chat_request.requested_faculty_id)
    reason = str(getattr(analysis, "clarification_reason", "") or "").strip()
    answer = (
        "Am nevoie de o clarificare ca sa aleg sursa oficiala corecta. "
        "Precizeaza tema exacta: orar, programul secretariatului, program de studii, admitere, burse sau regulamente."
    )
    if reason:
        answer = f"{answer} Motiv: {reason}."

    return {
        "answer": answer,
        "sources": [],
        "matched_faculty": faculty["name"],
        "matched_faculty_id": faculty["id"],
        "confidence": "low",
        "confidence_score": 25,
        "confidence_reason": reason or "Ollama query analysis a marcat intrebarea ca necesitand clarificare.",
        "live_verified": False,
        "query_profile": {
            "intent": getattr(analysis, "intent", "clarification") or "clarification",
            "policy_question": bool(getattr(analysis, "is_policy_question", False)),
            "normalized_question": getattr(analysis, "corrected_question", "") or normalize_retrieval_text(chat_request.question),
            "corrections": list(getattr(analysis, "corrections", ()) or ()),
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
            "Inca indexez sursele oficiale UVT. "
            f"Progres curent: {progress}%. {message} "
            "Raspunsurile vor fi disponibile dupa ce se termina indexarea."
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
