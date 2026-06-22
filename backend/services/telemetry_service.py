from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

from core.config import BACKEND_DIR

LOG_DIR = BACKEND_DIR / "logs"
CHAT_REQUEST_LOG = LOG_DIR / "chat_requests.jsonl"
CHAT_LOG_LOCK = threading.Lock()


def new_request_id() -> str:
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _payload_dict(payload) -> dict:
    return payload if isinstance(payload, dict) else {}


def _question_length(payload) -> int:
    value = _payload_dict(payload).get("question")
    return len(str(value or ""))


def _source_count(response_payload: dict) -> int:
    evidence = response_payload.get("evidence") if isinstance(response_payload.get("evidence"), dict) else {}
    if evidence.get("source_count") is not None:
        try:
            return int(evidence.get("source_count") or 0)
        except (TypeError, ValueError):
            return 0
    sources = response_payload.get("sources")
    return len(sources) if isinstance(sources, list) else 0


def _verified_source_count(response_payload: dict) -> int:
    evidence = response_payload.get("evidence") if isinstance(response_payload.get("evidence"), dict) else {}
    if evidence.get("verified_source_count") is not None:
        try:
            return int(evidence.get("verified_source_count") or 0)
        except (TypeError, ValueError):
            return 0
    sources = response_payload.get("sources")
    if not isinstance(sources, list):
        return 0
    return sum(1 for source in sources if isinstance(source, dict) and source.get("verified"))


def build_chat_request_record(
    request_id: str,
    request_payload,
    response_payload,
    total_latency_ms: int,
) -> dict:
    request_payload = _payload_dict(request_payload)
    response_payload = _payload_dict(response_payload)
    query_profile = response_payload.get("query_profile")
    query_profile = query_profile if isinstance(query_profile, dict) else {}

    record = {
        "timestamp": utc_now_iso(),
        "request_id": request_id,
        "question_length": _question_length(request_payload),
        "faculty_id": str(request_payload.get("faculty_id") or "uvt"),
        "matched_faculty_id": str(response_payload.get("matched_faculty_id") or ""),
        "detected_intent": str(query_profile.get("intent") or ""),
        "retrieval_backend": str(response_payload.get("retrieval_backend") or ""),
        "generation_mode": str(response_payload.get("generation_mode") or ""),
        "confidence": str(response_payload.get("confidence") or ""),
        "confidence_score": response_payload.get("confidence_score"),
        "source_count": _source_count(response_payload),
        "verified_source_count": _verified_source_count(response_payload),
        "live_verified": bool(response_payload.get("live_verified")),
        "total_latency_ms": int(total_latency_ms),
    }
    generation_error = str(response_payload.get("generation_error") or "").strip()
    if generation_error:
        record["generation_error"] = generation_error
    return record


def write_jsonl_record(path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with CHAT_LOG_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def log_chat_request(
    request_id: str,
    request_payload,
    response_payload,
    total_latency_ms: int,
    log_path=CHAT_REQUEST_LOG,
) -> None:
    write_jsonl_record(
        log_path,
        build_chat_request_record(request_id, request_payload, response_payload, total_latency_ms),
    )


def log_chat_exception(
    request_id: str,
    request_payload,
    total_latency_ms: int,
    exc: Exception,
    log_path=CHAT_REQUEST_LOG,
) -> None:
    record = {
        "timestamp": utc_now_iso(),
        "request_id": request_id,
        "question_length": _question_length(request_payload),
        "faculty_id": str(_payload_dict(request_payload).get("faculty_id") or "uvt"),
        "matched_faculty_id": "",
        "detected_intent": "",
        "retrieval_backend": "",
        "generation_mode": "exception",
        "confidence": "",
        "confidence_score": None,
        "source_count": 0,
        "verified_source_count": 0,
        "live_verified": False,
        "total_latency_ms": int(total_latency_ms),
        "generation_error": f"{type(exc).__name__}: {exc}",
    }
    write_jsonl_record(log_path, record)
