from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from faculties import FACULTIES
from page_index import (
    MAX_CHUNKS_PER_PAGE,
    MAX_PAGE_TEXT_CHARS,
    build_chunk_entries_from_pages,
    build_index_document,
    chunk_text,
    detect_page_type,
    normalize_index_document,
    normalize_url,
)


class PageIndexTests(unittest.TestCase):
    def test_normalize_url_canonicalizes_host_and_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_url("https://www.info.uvt.ro/orare/"),
            "https://info.uvt.ro/orare",
        )

    def test_detect_page_type_prefers_policy_methodology(self) -> None:
        page_type = detect_page_type(
            "https://www.uvt.ro/regulamente/metodologie-burse.pdf",
            "Metodologie privind acordarea burselor",
            "Art. 5 reguli de cumulare bursa studenti eligibilitate.",
        )
        self.assertEqual(page_type, "regulamente")

    def test_build_chunks_includes_required_vector_payload_fields(self) -> None:
        chunks = build_chunk_entries_from_pages(
            [
                {
                    "url": "https://info.uvt.ro/orare/",
                    "title": "Orare",
                    "text": "Orarul facultatii de informatica este publicat pe pagina oficiala. " * 30,
                }
            ],
            FACULTIES,
            built_at="2026-01-01T00:00:00+00:00",
        )

        self.assertGreaterEqual(len(chunks), 1)
        required_keys = {"chunk_id", "faculty_id", "page_type", "title", "url", "chunk_text", "last_indexed"}
        self.assertTrue(required_keys.issubset(chunks[0]))
        self.assertEqual(chunks[0]["faculty_id"], "info")
        self.assertEqual(chunks[0]["page_type"], "orar")

    def test_chunk_text_bounds_huge_unspaced_text(self) -> None:
        chunks = chunk_text("x" * (MAX_PAGE_TEXT_CHARS * 4))

        self.assertLessEqual(len(chunks), MAX_CHUNKS_PER_PAGE)
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))

    def test_build_chunks_caps_number_of_chunks_per_large_page(self) -> None:
        chunks = build_chunk_entries_from_pages(
            [
                {
                    "url": "https://uvt.ro/pagina-mare",
                    "title": "Pagina mare",
                    "text": "informatie oficiala " * 100000,
                }
            ],
            FACULTIES,
            built_at="2026-01-01T00:00:00+00:00",
        )

        self.assertLessEqual(len(chunks), MAX_CHUNKS_PER_PAGE)

    def test_normalize_index_document_removes_duplicate_chunks_before_vector_indexing(self) -> None:
        document = build_index_document(
            [
                {
                    "url": "https://uvt.ro/duplicat",
                    "title": "Duplicat",
                    "text": "aceeasi informatie oficiala " * 40,
                },
                {
                    "url": "https://www.uvt.ro/duplicat/",
                    "title": "Duplicat",
                    "text": "aceeasi informatie oficiala " * 40,
                },
            ],
            FACULTIES,
            built_at="2026-01-01T00:00:00+00:00",
        )

        normalized = normalize_index_document(document)

        self.assertLess(normalized["chunk_count"], document["chunk_count"])
        self.assertEqual(
            len({chunk["chunk_id"] for chunk in normalized["chunks"]}),
            normalized["chunk_count"],
        )


if __name__ == "__main__":
    unittest.main()
