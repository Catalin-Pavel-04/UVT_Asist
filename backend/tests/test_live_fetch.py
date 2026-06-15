from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import live_fetch as live_fetch_module


class FakeResponse:
    def __init__(self, url: str, text: str, content_type: str = "text/plain") -> None:
        self.url = url
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, url: str, timeout=None) -> FakeResponse:
        return self.response


class LiveFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        live_fetch_module.clear_fetch_caches()

    def test_index_mode_preserves_later_document_text(self) -> None:
        marker = "LATE_DOCUMENT_MARKER"
        text = ("a" * (live_fetch_module.MAX_TEXT_LENGTH + 500)) + marker
        response = FakeResponse("https://uvt.ro/document.txt", text)

        with patch.object(live_fetch_module, "get_session", return_value=FakeSession(response)):
            page = live_fetch_module.fetch_page("https://uvt.ro/document.txt", index_mode=True)

        self.assertIn(marker, page["text"])

    def test_index_mode_preserves_later_html_text_up_to_index_limit(self) -> None:
        marker = "LATE_HTML_MARKER"
        text = ("a" * (live_fetch_module.MAX_TEXT_LENGTH + 500)) + marker
        response = FakeResponse("https://uvt.ro/pagina", f"<html><body>{text}</body></html>", "text/html")

        with patch.object(live_fetch_module, "get_session", return_value=FakeSession(response)):
            page = live_fetch_module.fetch_page("https://uvt.ro/pagina", index_mode=True)

        self.assertIn(marker, page["text"])

    def test_live_mode_keeps_shorter_default_document_text(self) -> None:
        marker = "LATE_DOCUMENT_MARKER"
        text = ("a" * (live_fetch_module.MAX_TEXT_LENGTH + 500)) + marker
        response = FakeResponse("https://uvt.ro/document-live.txt", text)

        with patch.object(live_fetch_module, "get_session", return_value=FakeSession(response)):
            page = live_fetch_module.fetch_page("https://uvt.ro/document-live.txt")

        self.assertNotIn(marker, page["text"])

    def test_invalid_pdf_body_is_not_sent_to_pdf_parser(self) -> None:
        response = FakeResponse("https://uvt.ro/broken.pdf", "406: Not Acceptable", "text/plain")

        with (
            patch.object(live_fetch_module, "get_session", return_value=FakeSession(response)),
            patch.object(
                live_fetch_module,
                "extract_pdf_text_with_fallback",
                side_effect=AssertionError("Invalid PDF body should not be parsed."),
            ),
        ):
            page = live_fetch_module.fetch_page("https://uvt.ro/broken.pdf", index_mode=True)

        self.assertEqual(page["type"], "invalid_pdf")
        self.assertEqual(page["text"], "")

    def test_html_error_at_pdf_url_is_not_indexed_as_html(self) -> None:
        response = FakeResponse(
            "https://uvt.ro/broken-html.pdf",
            "<html><title>Eroare</title><body>406 Not Acceptable</body></html>",
            "text/html",
        )

        with patch.object(live_fetch_module, "get_session", return_value=FakeSession(response)):
            page = live_fetch_module.fetch_page("https://uvt.ro/broken-html.pdf", index_mode=True)

        self.assertEqual(page["type"], "invalid_pdf")
        self.assertEqual(page["text"], "")


if __name__ == "__main__":
    unittest.main()
