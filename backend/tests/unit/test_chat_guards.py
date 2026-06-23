from __future__ import annotations

import pytest

from services.chat_guards import (
    empty_question_payload,
    is_unsupported_question,
    is_vague_question,
    unsupported_question_payload,
    vague_question_payload,
)
from services.chat_models import ChatRequest


def test_empty_question_payload_is_low_confidence() -> None:
    payload = empty_question_payload()

    assert payload["confidence"] == "low"
    assert payload["confidence_score"] == 0
    assert payload["retrieval_backend"] == "none"
    assert payload["generation_mode"] == "none"


def test_vague_question_without_history_returns_clarification_payload() -> None:
    request = ChatRequest(question="ajutor", requested_faculty_id="uvt", history=[])

    assert is_vague_question(request.question)
    payload = vague_question_payload(request)

    assert payload["confidence"] == "low"
    assert payload["retrieval_backend"] == "clarification"
    assert payload["query_profile"]["intent"] == "clarification"


@pytest.mark.parametrize(
    "question",
    [
        "Care este nota mea?",
        "Care este parola mea?",
        "Care va fi media minima de admitere de anul viitor?",
    ],
)
def test_unsupported_questions_return_unsupported_guard(question: str) -> None:
    request = ChatRequest(question=question, requested_faculty_id="uvt", history=[])

    assert is_unsupported_question(question)
    payload = unsupported_question_payload(request)

    assert payload["confidence"] == "low"
    assert payload["retrieval_backend"] == "unsupported_guard"
    assert payload["query_profile"]["intent"] == "unsupported"
