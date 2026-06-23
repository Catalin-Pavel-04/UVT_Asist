from __future__ import annotations

import json

from services.telemetry_service import build_chat_request_record, log_chat_exception, log_chat_request


def test_chat_telemetry_records_metadata_without_question_text() -> None:
    request_payload = {"question": "Unde gasesc orarul?", "faculty_id": "info"}
    response_payload = {
        "matched_faculty_id": "info",
        "query_profile": {"intent": "orar"},
        "retrieval_backend": "qdrant",
        "generation_mode": "local_source_navigation",
        "confidence": "high",
        "confidence_score": 91,
        "sources": [{"url": "https://info.uvt.ro/orare", "verified": True}],
        "live_verified": True,
        "evidence": {"source_count": 1, "verified_source_count": 1},
    }

    record = build_chat_request_record("req-1", request_payload, response_payload, 123)

    assert record["request_id"] == "req-1"
    assert record["question_length"] == len("Unde gasesc orarul?")
    assert "question" not in record
    assert "Unde gasesc orarul?" not in json.dumps(record, ensure_ascii=False)
    assert record["detected_intent"] == "orar"
    assert record["retrieval_backend"] == "qdrant"
    assert record["generation_mode"] == "local_source_navigation"
    assert record["confidence"] == "high"
    assert record["source_count"] == 1
    assert record["verified_source_count"] == 1
    assert record["live_verified"] is True
    assert record["total_latency_ms"] == 123


def test_chat_telemetry_writes_jsonl(tmp_path) -> None:
    log_path = tmp_path / "chat_requests.jsonl"

    log_chat_request(
        "req-2",
        {"question": "Secretariat?", "faculty_id": "info"},
        {
            "matched_faculty_id": "info",
            "query_profile": {"intent": "contact"},
            "retrieval_backend": "local_json_lexical",
            "generation_mode": "fallback_low_evidence",
            "confidence": "low",
            "confidence_score": 20,
            "sources": [],
            "live_verified": False,
        },
        42,
        log_path=log_path,
    )

    rows = log_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["request_id"] == "req-2"


def test_chat_exception_telemetry_records_exception_mode_without_question_text(tmp_path) -> None:
    log_path = tmp_path / "chat_exceptions.jsonl"

    log_chat_exception(
        "req-3",
        {"question": "Care este parola mea?", "faculty_id": "uvt"},
        17,
        RuntimeError("boom"),
        log_path=log_path,
    )

    [row] = log_path.read_text(encoding="utf-8").splitlines()
    record = json.loads(row)

    assert record["request_id"] == "req-3"
    assert record["question_length"] == len("Care este parola mea?")
    assert record["generation_mode"] == "exception"
    assert record["source_count"] == 0
    assert record["live_verified"] is False
    assert "RuntimeError: boom" == record["generation_error"]
    assert "Care este parola mea?" not in row
