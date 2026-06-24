from __future__ import annotations

import pytest

import api.routes_chat as routes_chat
import api.routes_feedback as routes_feedback
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_chat_empty_question_contract(monkeypatch, client) -> None:
    monkeypatch.setattr(
        routes_chat.chat_service,
        "handle_chat",
        lambda payload: (
            {
                "answer": "Intrebarea este goala.",
                "sources": [],
                "matched_faculty": "UVT (general)",
                "matched_faculty_id": "uvt",
                "confidence": "low",
                "confidence_score": 0,
                "confidence_reason": "Nu a fost primita nicio intrebare.",
                "live_verified": False,
                "query_profile": {
                    "intent": "none",
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
            },
            200,
        ),
    )

    response = client.post("/chat", json={"question": "", "faculty_id": "uvt"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["answer"]
    assert payload["confidence"] == "low"
    assert payload["retrieval_backend"] == "none"


def test_feedback_accepts_minimal_payload(monkeypatch, client) -> None:
    monkeypatch.setattr(routes_feedback, "handle_feedback", lambda payload: {"ok": True})

    response = client.post("/feedback", json={"feedback": "up"})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
