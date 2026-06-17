from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evaluation.rag_eval import build_evaluation_result, calculate_metrics, top_url_match


class EvaluationTests(unittest.TestCase):
    def test_top1_and_top3_url_matching_uses_expected_fragments(self) -> None:
        sources = [
            {"url": "https://uvt.ro/"},
            {"url": "https://info.uvt.ro/contact/"},
            {"url": "https://info.uvt.ro/orare/"},
        ]

        self.assertFalse(top_url_match(sources, ["info.uvt.ro/orare"], depth=1))
        self.assertTrue(top_url_match(sources, ["info.uvt.ro/orare"], depth=3))

    def test_metrics_are_calculated_from_mock_results(self) -> None:
        question = {
            "id": "orar_info_001",
            "category": "orar",
            "faculty_id": "info",
            "question": "Unde găsesc orarul?",
            "expected_url_contains": ["info.uvt.ro/orare"],
            "should_have_answer": True,
        }
        good = build_evaluation_result(
            question,
            {
                "answer": "Orarul este pe pagina oficială.",
                "confidence": "high",
                "confidence_score": 92,
                "sources": [{"title": "Orare", "url": "https://info.uvt.ro/orare/"}],
            },
            latency_seconds=1.0,
        )
        low = build_evaluation_result(
            {**question, "id": "orar_info_002"},
            {
                "answer": "Sursele sunt insuficiente.",
                "confidence": "low",
                "confidence_score": 20,
                "sources": [{"title": "UVT", "url": "https://uvt.ro/"}],
            },
            latency_seconds=3.0,
        )

        metrics = calculate_metrics([good, low])

        self.assertEqual(metrics["total_questions"], 2)
        self.assertEqual(metrics["answered_count"], 2)
        self.assertEqual(metrics["low_confidence_count"], 1)
        self.assertEqual(metrics["top1_url_match_count"], 1)
        self.assertEqual(metrics["top3_url_match_count"], 1)
        self.assertEqual(metrics["average_latency_seconds"], 2.0)
        self.assertEqual(metrics["median_latency_seconds"], 2.0)

    def test_unanswerable_questions_are_counted_when_low_confidence(self) -> None:
        question = {
            "id": "unanswerable_001",
            "category": "întrebări fără răspuns sigur în sursele oficiale",
            "faculty_id": "uvt",
            "question": "Care va fi media minimă de admitere de anul viitor?",
            "expected_url_contains": [],
            "should_have_answer": False,
        }
        result = build_evaluation_result(
            question,
            {
                "answer": "Sursele oficiale disponibile nu sunt suficiente pentru un răspuns sigur.",
                "confidence": "low",
                "confidence_score": 10,
                "sources": [],
                "evidence": {"answerable": False},
            },
            latency_seconds=0.5,
        )

        metrics = calculate_metrics([result])

        self.assertTrue(result["expected_unanswerable_handled"])
        self.assertEqual(metrics["expected_unanswerable_handled_count"], 1)


if __name__ == "__main__":
    unittest.main()
