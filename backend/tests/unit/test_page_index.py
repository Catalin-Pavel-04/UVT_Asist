from __future__ import annotations

import pytest

from page_index import chunk_text, detect_page_type


@pytest.mark.parametrize(
    ("url", "title", "text", "expected_page_type"),
    [
        ("https://info.uvt.ro/orare", "Orare", "Programarea cursurilor pentru studenti.", "orar"),
        ("https://uvt.ro/contact", "Contact", "Telefon, e-mail si program cu publicul.", "contact"),
        ("https://admitere.uvt.ro/proces", "Admitere UVT", "Informatii pentru candidat si inscriere.", "admitere"),
        ("https://uvt.ro/metodologie-burse.pdf", "Metodologie burse", "Art. 5 reguli de cumulare.", "regulamente"),
        ("https://uvt.ro/cazare", "Cazare studenti", "Informatii despre camine si taxe.", "studenti"),
    ],
)
def test_detect_page_type_from_url_title_and_text(
    url: str,
    title: str,
    text: str,
    expected_page_type: str,
) -> None:
    assert detect_page_type(url, title, text) == expected_page_type


def test_chunk_text_returns_non_empty_chunks_and_respects_max_chunks() -> None:
    text = " ".join(f"cuvant{i}" for i in range(500))

    chunks = chunk_text(text, chunk_size=220, overlap=40, max_chunks=3)

    assert 1 <= len(chunks) <= 3
    assert all(chunk.strip() for chunk in chunks)
