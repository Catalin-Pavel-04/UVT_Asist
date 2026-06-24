from __future__ import annotations

import re

from core.config import MAX_QUESTION_CHARS
from rag.text_normalization import normalize as normalize_retrieval_text
from services.chat_models import ChatRequest, GENERAL_FACULTY_ID

MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 500


def normalize_payload(payload) -> dict:
    return payload if isinstance(payload, dict) else {}


def compact_text(value, max_chars: int) -> str:
    return " ".join(str(value or "").split()).strip()[:max_chars]


def normalize_match_text(text: str) -> str:
    normalized = normalize_retrieval_text(text)
    normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


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


def parse_chat_request(payload) -> ChatRequest:
    payload = normalize_payload(payload)
    return ChatRequest(
        question=compact_text(payload.get("question"), MAX_QUESTION_CHARS),
        requested_faculty_id=compact_text(payload.get("faculty_id") or GENERAL_FACULTY_ID, 64),
        history=normalize_history(payload.get("history")),
    )
