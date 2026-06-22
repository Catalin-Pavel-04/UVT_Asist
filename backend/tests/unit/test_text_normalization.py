from __future__ import annotations

from rag.text_normalization import correct_query_terms, normalize, tokenize


def test_normalize_removes_diacritics_and_compacts_spaces() -> None:
    assert normalize("  \u0218coal\u0103   \u021Aar\u0103 \n UVT  ") == "scoala tara uvt"


def test_tokenize_removes_stopwords_by_default() -> None:
    assert tokenize("Unde gasesc orarul la secretariat?") == ["orar", "secretariat"]


def test_tokenize_can_keep_stopwords() -> None:
    tokens = tokenize("Unde gasesc orarul la secretariat?", remove_stopwords=False)

    assert "unde" in tokens
    assert "gasesc" in tokens
    assert "orar" in tokens


def test_typo_correction_handles_schedule_and_secretariat_terms() -> None:
    schedule, _ = correct_query_terms("Unde este orrarul?")
    secretariat, _ = correct_query_terms("secreteriat")

    assert "orar" in schedule
    assert "orrar" not in schedule
    assert secretariat == "secretariat"
