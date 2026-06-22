from __future__ import annotations

import pytest

from rag.intent_detection import detect_intent, detect_policy_question
from rag.query_analysis import analyze_query_deterministic


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("Unde gasesc orarul?", "orar"),
        ("Pot beneficia de 2 burse?", "regulamente"),
        ("Care este programul secretariatului?", "contact"),
        ("Unde gasesc informatii despre admitere?", "admitere"),
        ("Ce metodologie se aplica pentru credite de voluntariat?", "regulamente"),
    ],
)
def test_detect_intent_for_core_student_questions(question: str, expected_intent: str) -> None:
    assert detect_intent(question) == expected_intent


def test_policy_detection_for_scholarship_cumulation() -> None:
    assert detect_policy_question("Poate un student sa primeasca 2 burse?", "regulamente")


def test_deterministic_analysis_expands_policy_terms() -> None:
    analysis = analyze_query_deterministic("Cum se depune dosarul pentru creditele de voluntariat?")

    assert analysis.intent == "regulamente"
    assert analysis.is_policy_question is True
    assert "voluntariat" in analysis.expanded_tokens
    assert "portofoliu" in analysis.expanded_tokens
