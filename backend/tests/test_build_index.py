from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import build_index as build_index_module
from build_index import discover_sitemap_urls
from page_index import MAX_PAGE_TEXT_CHARS


class BuildIndexTests(unittest.TestCase):
    def test_discover_sitemap_urls_follows_sitemap_indexes_and_filters_domains(self) -> None:
        locations = {
            "https://info.uvt.ro/sitemap.xml": [
                "https://info.uvt.ro/page-sitemap.xml",
                "https://example.com/not-official",
            ],
            "https://info.uvt.ro/wp-sitemap.xml": [],
            "https://info.uvt.ro/page-sitemap.xml": [
                "https://info.uvt.ro/orare/",
                "https://info.uvt.ro/contact/",
                "https://other.uvt.ro/contact/",
            ],
        }

        with patch("build_index.fetch_sitemap_locations", side_effect=lambda url: locations.get(url, [])):
            urls = discover_sitemap_urls(["https://info.uvt.ro/"], max_urls=10)

        self.assertEqual(urls, ["https://info.uvt.ro/orare/", "https://info.uvt.ro/contact/"])

    def test_zero_max_urls_means_no_sitemap_cap(self) -> None:
        locations = {
            "https://info.uvt.ro/sitemap.xml": [
                "https://info.uvt.ro/a/",
                "https://info.uvt.ro/b/",
                "https://info.uvt.ro/c/",
            ],
            "https://info.uvt.ro/wp-sitemap.xml": [],
        }

        with patch("build_index.fetch_sitemap_locations", side_effect=lambda url: locations.get(url, [])):
            urls = discover_sitemap_urls(["https://info.uvt.ro/"], max_urls=0)

        self.assertEqual(urls, ["https://info.uvt.ro/a/", "https://info.uvt.ro/b/", "https://info.uvt.ro/c/"])

    def test_fetch_pages_keeps_indexing_when_one_url_crashes(self) -> None:
        def fake_fetch_page(url: str, **kwargs) -> dict:
            self.assertTrue(kwargs.get("index_mode"))
            if url.endswith("/bad"):
                raise RuntimeError()
            return {"url": url, "title": url, "text": "continut oficial", "type": "html"}

        with patch.object(build_index_module, "fetch_page", side_effect=fake_fetch_page):
            pages = build_index_module.fetch_pages_with_errors(
                ["https://uvt.ro/good", "https://uvt.ro/bad"],
                max_workers=1,
            )

        self.assertEqual(pages[0]["text"], "continut oficial")
        self.assertEqual(pages[1]["type"], "error")
        self.assertEqual(pages[1]["error"], "RuntimeError")

    def test_compact_page_for_index_uses_document_text_limit(self) -> None:
        marker = "DOCUMENTE_LATE_MARKER"
        page = build_index_module.compact_page_for_index({
            "url": "https://uvt.ro/wp-content/uploads/metodologie.pdf",
            "title": "Metodologie burse",
            "text": ("a" * (MAX_PAGE_TEXT_CHARS + 2000)) + marker,
            "type": "pdf",
        })

        self.assertIn(marker, page["text"])

    def test_build_index_emits_progress_events(self) -> None:
        events: list[dict] = []
        index_document = {
            "schema_version": 2,
            "page_count": 1,
            "chunk_count": 1,
            "chunks": [
                {
                    "chunk_id": "uvt-1",
                    "faculty_id": "uvt",
                    "page_type": "general",
                    "title": "UVT",
                    "url": "https://uvt.ro/",
                    "chunk_text": "Text oficial.",
                }
            ],
        }

        def fake_rebuild_vector_index(document, recreate=True, progress=None):
            if progress:
                progress(1, 1)
            return {
                "collection": "test",
                "indexed_count": 1,
                "chunk_count": 1,
                "vector_size": 768,
            }

        with (
            patch.object(build_index_module, "FACULTIES", [{"id": "uvt", "name": "UVT", "base_urls": ["https://uvt.ro/"]}]),
            patch.object(build_index_module, "discover_faculty_urls", return_value=["https://uvt.ro/"]),
            patch.object(build_index_module, "fetch_pages_with_errors", return_value=[{"url": "https://uvt.ro/", "title": "UVT", "text": "Text oficial."}]),
            patch.object(build_index_module, "build_index_document", return_value=dict(index_document)),
            patch.object(build_index_module, "rebuild_vector_index", side_effect=fake_rebuild_vector_index),
            patch.object(build_index_module, "save_index"),
        ):
            document = build_index_module.build_index(progress=events.append)

        event_names = [event["event"] for event in events]
        self.assertEqual(document["vector_index"]["indexed_count"], 1)
        self.assertIn("started", event_names)
        self.assertIn("faculty_fetched", event_names)
        self.assertIn("json_built", event_names)
        self.assertIn("vector_progress", event_names)
        self.assertEqual(event_names[-1], "saved")


if __name__ == "__main__":
    unittest.main()
