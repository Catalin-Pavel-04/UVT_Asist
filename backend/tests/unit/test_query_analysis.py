from __future__ import annotations

import pytest

import rag.query_analysis as query_analysis_module
from rag.intent_detection import detect_intent, detect_policy_question
from rag.query_analysis import analyze_query


@pytest.fixture(autouse=True)
def clear_query_rewrite_cache() -> None:
    query_analysis_module._QUERY_REWRITE_CACHE.clear()


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
def test_detect_intent_helper_for_core_student_questions(question: str, expected_intent: str) -> None:
    assert detect_intent(question) == expected_intent


def test_policy_detection_helper_for_scholarship_cumulation() -> None:
    assert detect_policy_question("Poate un student sa primeasca 2 burse?", "regulamente")


def test_ollama_corrects_schedule_typo_and_faculty_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: True)
    monkeypatch.setattr(
        query_analysis_module,
        "ask_ollama_json",
        lambda *args, **kwargs: {
            "corrected_question": "unde gasesc orarul la info",
            "intent": "orar",
            "is_policy_question": False,
            "keywords": ["orar", "info"],
            "faculty_hint": "info",
            "requires_clarification": False,
            "clarification_reason": "",
        },
    )

    analysis = analyze_query("unde gasesc orrarul la info")

    assert analysis.original_question == "unde gasesc orrarul la info"
    assert "orar" in analysis.corrected_question
    assert analysis.faculty_hint == "info"
    assert analysis.intent == "orar"
    assert analysis.rewrite_source == "ollama"


def test_ollama_corrects_secretariat_typo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: True)
    monkeypatch.setattr(
        query_analysis_module,
        "ask_ollama_json",
        lambda *args, **kwargs: {
            "corrected_question": "secretariat info",
            "intent": "contact",
            "is_policy_question": False,
            "keywords": ["secretariat", "info"],
            "faculty_hint": "info",
            "requires_clarification": False,
            "clarification_reason": "",
        },
    )

    analysis = analyze_query("secreteriat info")

    assert "secretariat" in analysis.corrected_question
    assert analysis.faculty_hint == "info"


def test_ollama_marks_scholarship_cumulation_as_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: True)
    monkeypatch.setattr(
        query_analysis_module,
        "ask_ollama_json",
        lambda *args, **kwargs: {
            "corrected_question": "pot primi doua burse",
            "intent": "regulamente",
            "is_policy_question": True,
            "keywords": ["burse", "cumulare"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        },
    )

    assert analyze_query("pot primi doua burse?").is_policy_question is True


def test_ollama_can_request_clarification_for_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: True)
    monkeypatch.setattr(
        query_analysis_module,
        "ask_ollama_json",
        lambda *args, **kwargs: {
            "corrected_question": "program",
            "intent": "general",
            "is_policy_question": False,
            "keywords": ["program"],
            "faculty_hint": "",
            "requires_clarification": True,
            "clarification_reason": "program poate insemna orar, program secretariat sau program de studii",
        },
    )

    analysis = analyze_query("program")

    assert analysis.requires_clarification is True
    assert "program" in analysis.clarification_reason


def test_invalid_json_shape_falls_back_to_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: True)
    monkeypatch.setattr(query_analysis_module, "ask_ollama_json", lambda *args, **kwargs: ["not", "a", "dict"])

    analysis = analyze_query("unde gasesc orrarul la info")

    assert analysis.rewrite_source == "raw_fallback"
    assert analysis.corrected_question == "unde gasesc orrarul la info"
    assert analysis.intent == "general"


def test_ollama_unavailable_falls_back_to_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: True)

    def raise_unavailable(*args, **kwargs):
        raise RuntimeError("ollama unavailable")

    monkeypatch.setattr(query_analysis_module, "ask_ollama_json", raise_unavailable)

    analysis = analyze_query("secreteriat info")

    assert analysis.rewrite_source == "raw_fallback"
    assert analysis.corrected_question == "secreteriat info"
    assert analysis.corrections == ()


def test_raw_fallback_does_not_use_common_replacements_or_difflib(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: False)

    analysis = analyze_query("orrarul secreteriat")

    assert analysis.rewrite_source == "raw_fallback"
    assert analysis.corrected_question == "orrarul secreteriat"
    assert "orar" not in analysis.corrected_question
    assert "secretariat" not in analysis.corrected_question


def test_original_question_is_always_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: True)
    monkeypatch.setattr(
        query_analysis_module,
        "ask_ollama_json",
        lambda *args, **kwargs: {
            "corrected_question": "unde gasesc orarul la info",
            "intent": "orar",
            "is_policy_question": False,
            "keywords": ["orar"],
            "faculty_hint": "info",
            "requires_clarification": False,
            "clarification_reason": "",
        },
    )

    analysis = analyze_query("Unde gasesc orrarul la info?")

    assert analysis.original_question == "Unde gasesc orrarul la info?"


def test_query_rewrite_cache_reuses_valid_ollama_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_ollama(*args, **kwargs):
        calls["count"] += 1
        return {
            "corrected_question": "unde gasesc orarul",
            "intent": "orar",
            "is_policy_question": False,
            "keywords": ["orar"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }

    monkeypatch.setattr(query_analysis_module, "query_analysis_enabled", lambda: True)
    monkeypatch.setattr(query_analysis_module, "QUERY_REWRITE_CACHE_TTL", 600)
    monkeypatch.setattr(query_analysis_module, "ask_ollama_json", fake_ollama)

    first = analyze_query("Unde gasesc orarul?")
    second = analyze_query("  unde gasesc orarul?  ")

    assert calls["count"] == 1
    assert first.corrected_question == second.corrected_question
