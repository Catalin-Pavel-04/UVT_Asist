from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import evaluate_qa_1000_independent as evaluator


REQUIRED_DATASET_FIELDS = {
    "id",
    "category",
    "faculty_id",
    "question",
    "ideal_answer",
    "should_have_answer",
    "expected_confidence",
    "required_terms",
    "forbidden_terms",
}


def make_question(**overrides: object) -> dict:
    question = {
        "id": "q1",
        "category": "orar",
        "faculty_id": "info",
        "faculty_name": "Facultatea de Matematica si Informatica",
        "question": "Unde gasesc orarul?",
        "ideal_answer": "Studentul trebuie indrumat catre pagina oficiala de orare.",
        "should_have_answer": True,
        "answer_type": "source_navigation",
        "expected_intent": "schedule",
        "expected_page_type": "schedule",
        "expected_url_contains": ["info.uvt.ro/orare"],
        "expected_confidence": ["high"],
        "required_terms": ["orar"],
        "forbidden_terms": [],
        "difficulty": "easy",
        "notes": "",
    }
    question.update(overrides)
    return question


def make_payload(**overrides: object) -> dict:
    payload = {
        "answer": "Orarul este disponibil pe pagina oficiala de orare.",
        "confidence": "high",
        "confidence_score": 92,
        "confidence_reason": "Surse oficiale potrivite.",
        "query_profile": {"intent": "schedule"},
        "retrieval_backend": "qdrant",
        "generation_mode": "ollama",
        "evidence": {"answerable": True},
        "live_verified": False,
        "sources": [
            {
                "title": "Orare",
                "url": "https://info.uvt.ro/orare/",
                "page_type": "schedule",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_load_dataset_reads_metadata_and_questions(tmp_path: Path) -> None:
    dataset = {
        "metadata": {"name": "mock"},
        "questions": [make_question()],
    }
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")

    metadata, questions = evaluator.load_dataset(dataset_path)

    assert metadata == {"name": "mock"}
    assert len(questions) == 1
    assert questions[0]["id"] == "q1"


def test_independent_dataset_has_required_fields_when_present() -> None:
    dataset_path = Path("backend/data/evaluation/eval_qa_1000_independent.json")
    if not dataset_path.exists():
        pytest.skip("Datasetul independent local nu este prezent in workspace.")

    _, questions = evaluator.load_dataset(dataset_path)

    assert questions
    for index, question in enumerate(questions, start=1):
        missing = REQUIRED_DATASET_FIELDS - set(question)
        assert not missing, f"Intrebarea #{index} ({question.get('id')}) nu are campurile: {sorted(missing)}"


def test_normalize_text_removes_diacritics_and_extra_spacing() -> None:
    assert evaluator.normalize_text("  Întrebări   despre   bursă! ") == "intrebari despre bursa"


def test_required_terms_match_with_and_without_diacritics() -> None:
    text = "Informatiile despre bursa sunt in metodologie oficiala."

    assert evaluator.terms_present(text, ["bursă", "metodologie"]) == ["bursă", "metodologie"]


def test_forbidden_terms_are_detected() -> None:
    question = make_question(forbidden_terms=["garantat"])
    payload = make_payload(answer="Este garantat ca studentul primeste bursa.")

    result = evaluator.compare_result(question, payload, status_code=200, latency_seconds=1.0)

    assert result["forbidden_terms_found"] == ["garantat"]
    assert result["score"] == 80.0


def test_scoring_answerable_passes_with_top1_url_match() -> None:
    result = evaluator.compare_result(make_question(), make_payload(), status_code=200, latency_seconds=1.0)

    assert result["passed"] is True
    assert result["score"] == 100.0
    assert result["top1_url_match"] is True
    assert result["top3_url_match"] is True


def test_scoring_answerable_passes_with_top3_url_match() -> None:
    payload = make_payload(
        sources=[
            {"title": "UVT", "url": "https://uvt.ro/", "page_type": "home"},
            {"title": "Orare", "url": "https://info.uvt.ro/orare/", "page_type": "schedule"},
        ]
    )

    result = evaluator.compare_result(make_question(), payload, status_code=200, latency_seconds=1.0)

    assert result["passed"] is True
    assert result["top1_url_match"] is False
    assert result["top3_url_match"] is True
    assert result["score"] == pytest.approx(88.24)


def test_scoring_answerable_does_not_penalize_missing_expected_url() -> None:
    question = make_question(expected_url_contains=[])
    payload = make_payload(sources=[{"title": "Orare", "url": "https://example.test/orare", "page_type": "schedule"}])

    result = evaluator.compare_result(question, payload, status_code=200, latency_seconds=1.0)

    assert result["passed"] is True
    assert result["url_applicable"] is False
    assert result["top1_url_match"] is None
    assert result["score"] == 100.0


def test_scoring_unanswerable_passes_for_low_confidence_and_not_answerable() -> None:
    question = make_question(
        id="q_unanswerable",
        should_have_answer=False,
        expected_confidence=["low"],
        required_terms=[],
        forbidden_terms=["garantat"],
    )
    payload = make_payload(
        answer="Sursele oficiale nu sunt suficiente pentru un raspuns sigur.",
        confidence="low",
        confidence_score=15,
        sources=[],
        evidence={"answerable": False},
    )

    result = evaluator.compare_result(question, payload, status_code=200, latency_seconds=1.0)

    assert result["passed"] is True
    assert result["score"] == 100.0
    assert result["expected_unanswerable_handled"] is True


def test_scoring_unanswerable_fails_for_speculative_answer() -> None:
    question = make_question(
        id="q_speculative",
        should_have_answer=False,
        expected_confidence=["low"],
        required_terms=[],
        forbidden_terms=["garantat"],
    )
    payload = make_payload(
        answer="Este garantat ca regulamentul se va schimba anul viitor.",
        confidence="high",
        confidence_score=90,
        evidence={"answerable": True},
    )

    result = evaluator.compare_result(question, payload, status_code=200, latency_seconds=1.0)

    assert result["passed"] is False
    assert result["score"] == 0.0
    assert result["forbidden_terms_found"] == ["garantat"]


def test_latency_percentiles_are_interpolated() -> None:
    assert evaluator.percentile([1.0, 2.0, 3.0, 4.0], 75) == 3.25
    assert evaluator.percentile([1.0, 2.0, 3.0, 4.0], 95) == 3.85


def test_category_metrics_are_grouped() -> None:
    results = [
        evaluator.compare_result(make_question(id="q1", category="orar"), make_payload(), 200, 1.0),
        evaluator.compare_result(make_question(id="q2", category="burse"), make_payload(), 200, 2.0),
        evaluator.compare_result(
            make_question(id="q3", category="burse", forbidden_terms=["garantat"]),
            make_payload(answer="Este garantat."),
            200,
            3.0,
        ),
    ]

    metrics = evaluator.calculate_category_metrics(results)

    assert set(metrics) == {"burse", "orar"}
    assert metrics["orar"]["total_questions"] == 1
    assert metrics["burse"]["total_questions"] == 2
    assert metrics["burse"]["average_latency"] == 2.5


def test_write_markdown_summary_with_mock_data(tmp_path: Path) -> None:
    results = [
        evaluator.compare_result(make_question(id="q1"), make_payload(), 200, 1.0),
        evaluator.compare_result(
            make_question(id="q2", forbidden_terms=["garantat"]),
            make_payload(answer="Este garantat."),
            200,
            4.0,
        ),
    ]
    global_metrics = evaluator.calculate_metrics(results)
    category_metrics = evaluator.calculate_category_metrics(results)
    output_path = tmp_path / "summary.md"

    evaluator.write_markdown_summary(
        output_path,
        {"dataset": "mock.json", "backend_url": "http://127.0.0.1:5000"},
        global_metrics,
        category_metrics,
        results,
    )

    content = output_path.read_text(encoding="utf-8")
    assert "# Evaluare Q&A 1000 independent" in content
    assert "## Rezumat global" in content
    assert "## Top 20 esecuri" in content
    assert "nu sunt o garantie universala" in content
