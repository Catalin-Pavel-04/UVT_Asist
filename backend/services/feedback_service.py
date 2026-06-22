from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from core.config import BACKEND_DIR, MAX_FEEDBACK_SOURCES, MAX_FEEDBACK_TEXT_CHARS
from services.chat_service import compact_text, normalize_payload, unique_sources_from_chunks

LOG_FILE = BACKEND_DIR / "feedback_log.jsonl"
FEEDBACK_LOCK = threading.Lock()


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




def handle_feedback(payload) -> dict:
    append_feedback_record(payload)
    return {"ok": True}
