from __future__ import annotations

from rag.confidence import compute_confidence


ANALYSIS = {
    "intent": "orar",
    "is_policy_question": False,
    "page_type_preferences": ("orar", "general"),
}


def test_confidence_is_low_without_chunks() -> None:
    confidence = compute_confidence([], ANALYSIS)

    assert confidence["label"] == "low"
    assert confidence["score"] == 10


def test_confidence_is_medium_for_partial_direct_match() -> None:
    confidence = compute_confidence(
        [
            {
                "retrieval_score": 65,
                "url": "https://info.uvt.ro/orare",
                "page_type": "orar",
                "match_signals": ["lexical:2"],
            }
        ],
        ANALYSIS,
    )

    assert confidence["label"] == "medium"
    assert 52 <= confidence["score"] < 78


def test_confidence_is_high_for_strong_direct_match() -> None:
    confidence = compute_confidence(
        [
            {
                "retrieval_score": 105,
                "url": "https://info.uvt.ro/orare",
                "page_type": "orar",
                "match_signals": ["lexical:2", "all_terms", "schedule_exact_path"],
            }
        ],
        ANALYSIS,
    )

    assert confidence["label"] == "high"
    assert confidence["score"] >= 78
