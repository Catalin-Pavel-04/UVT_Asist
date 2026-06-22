from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core import config


class ConfigTests(unittest.TestCase):
    def test_env_helpers_apply_defaults_and_bounds(self) -> None:
        with patch.dict(os.environ, {
            "UVT_TEST_BOOL": "yes",
            "UVT_TEST_INT": "3",
            "UVT_TEST_FLOAT": "2.5",
        }, clear=False):
            self.assertTrue(config.env_bool("UVT_TEST_BOOL"))
            self.assertEqual(config.env_int("UVT_TEST_INT", "1", minimum=5), 5)
            self.assertEqual(config.env_float("UVT_TEST_FLOAT", "1.0"), 2.5)

    def test_env_int_can_keep_tolerant_legacy_parsing(self) -> None:
        with patch.dict(os.environ, {"UVT_TEST_BAD_INT": "bad"}, clear=False):
            self.assertEqual(config.env_int("UVT_TEST_BAD_INT", 7, strict=False), 7)

    def test_chat_runtime_settings_are_read_from_environment(self) -> None:
        with patch.dict(os.environ, {
            "MAX_QUESTION_CHARS": "10",
            "LIVE_VERIFY_ENABLED": "off",
            "LIVE_VERIFY_LIMIT": "-4",
            "CHAT_CACHE_VERSION": "contract-test",
        }, clear=False):
            settings = config.get_chat_runtime_settings()

        self.assertEqual(settings.max_question_chars, 120)
        self.assertFalse(settings.live_verify_enabled)
        self.assertEqual(settings.live_verify_limit, 0)
        self.assertEqual(settings.chat_cache_version, "contract-test")

    def test_relative_qdrant_path_resolves_under_repo_root(self) -> None:
        resolved = Path(config.resolve_repo_path("backend/data/qdrant_local"))

        self.assertTrue(resolved.is_absolute())
        self.assertEqual(resolved, config.REPO_ROOT / "backend" / "data" / "qdrant_local")


if __name__ == "__main__":
    unittest.main()
