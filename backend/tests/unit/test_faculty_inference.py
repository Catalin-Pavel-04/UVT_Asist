from __future__ import annotations

from page_index import detect_faculty_id
from services.chat_service import infer_faculty


FACULTIES = [
    {"id": "uvt", "name": "UVT", "base_urls": ["https://www.uvt.ro/"]},
    {"id": "info", "name": "Facultatea de Informatica", "base_urls": ["https://info.uvt.ro/"]},
]


def test_detect_faculty_id_from_url_host() -> None:
    assert detect_faculty_id("https://info.uvt.ro/orare", FACULTIES) == "info"
    assert detect_faculty_id("https://unknown.uvt.ro/pagina", FACULTIES) == "uvt"


def test_infer_faculty_does_not_guess_from_question_alias_without_ollama_hint() -> None:
    faculty = infer_faculty("uvt", "Unde gasesc orarul la info?", [])

    assert faculty["id"] == "uvt"


def test_infer_faculty_from_ollama_faculty_hint() -> None:
    faculty = infer_faculty("uvt", "Unde gasesc orarul la info?", [], analysis={"faculty_hint": "info"})

    assert faculty["id"] == "info"


def test_explicit_faculty_selection_is_preserved() -> None:
    faculty = infer_faculty("info", "Unde gasesc orarul?", [])

    assert faculty["id"] == "info"
