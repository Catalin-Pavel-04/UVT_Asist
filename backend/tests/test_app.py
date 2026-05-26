from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app as app_module


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        app_module.app.config.update(TESTING=True)
        app_module.RESPONSE_CACHE.clear()
        self.client = app_module.app.test_client()

    def test_incomplete_policy_fragments_are_rejected(self) -> None:
        self.assertTrue(app_module.looks_incomplete_evidence_unit(
            "Studentii pot beneficia de burse numai de la una dintre institutii, cu conditia ca numarul total sa nu depaseasca anii de"
        ))
        self.assertFalse(app_module.looks_incomplete_evidence_unit(
            "Bursele prevazute la art 2 alin 4 pot fi cumulate cu alte burse."
        ))

    def test_chat_handles_non_object_json_without_500(self) -> None:
        response = self.client.post("/chat", json=["not", "an", "object"])

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(payload["retrieval_backend"], "none")

    def test_low_evidence_skips_llm_generation(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "general",
                "is_policy_question": False,
                "corrected_question": "ceva imposibil",
                "tokens": [],
                "expanded_tokens": [],
                "corrections": [],
            },
            "chunks": [],
            "confidence": "low",
            "confidence_score": 10,
            "confidence_reason": "Nu exista dovezi.",
            "retrieval_backend": "local_json_lexical",
        }

        with (
            patch.object(app_module, "load_index", return_value={"built_at": "test", "chunks": []}),
            patch.object(app_module, "get_vector_index_status", return_value={"points_count": 0}),
            patch.object(app_module, "rank_index", return_value=retrieval_result),
            patch.object(app_module, "ask_ollama", side_effect=AssertionError("LLM should not be called")),
        ):
            response = self.client.post("/chat", json={"question": "ceva imposibil", "faculty_id": "uvt"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["generation_mode"], "fallback_low_evidence")
        self.assertEqual(payload["sources"], [])
        self.assertFalse(payload["evidence"]["answerable"])

    def test_navigation_question_uses_deterministic_answer_without_llm(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "orar",
                "is_policy_question": False,
                "corrected_question": "orar",
                "tokens": ["orar"],
                "expanded_tokens": ["orar", "orare"],
                "corrections": [],
            },
            "chunks": [
                {
                    "chunk_id": "schedule",
                    "faculty_id": "info",
                    "page_type": "orar",
                    "title": "Orare - Facultatea de Informatica",
                    "url": "https://info.uvt.ro/orare",
                    "chunk_text": "Orarul este publicat pe pagina Orare.",
                    "retrieval_score": 120,
                    "match_signals": ["lexical:1", "page_type:orar", "schedule_exact_path"],
                }
            ],
            "confidence": "high",
            "confidence_score": 95,
            "confidence_reason": "Potrivire directa.",
            "retrieval_backend": "local_json_lexical",
        }

        with (
            patch.object(app_module, "load_index", return_value={"built_at": "test", "chunks": []}),
            patch.object(app_module, "get_vector_index_status", return_value={"points_count": 1}),
            patch.object(app_module, "rank_index", return_value=retrieval_result),
            patch.object(app_module, "live_verify_retrieval", return_value=(retrieval_result["chunks"], False)),
            patch.object(app_module, "ask_ollama", side_effect=AssertionError("LLM should not be called")),
        ):
            response = self.client.post("/chat", json={"question": "Unde gasesc orarul?", "faculty_id": "info"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["generation_mode"], "deterministic_orar")
        self.assertTrue(payload["evidence"]["answerable"])
        self.assertEqual(payload["evidence"]["top_source"]["url"], "https://info.uvt.ro/orare")
        self.assertIn("https://info.uvt.ro/orare", payload["answer"])

    def test_policy_answer_extracts_relevant_rules_from_evidence(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "regulamente",
                "is_policy_question": True,
                "corrected_question": "student beneficia 2 burse",
                "tokens": ["student", "beneficia", "2", "burse"],
                "expanded_tokens": ["student", "beneficia", "2", "burse", "cumulare"],
                "corrections": [],
            },
            "chunks": [
                {
                    "chunk_id": "burse",
                    "faculty_id": "uvt",
                    "page_type": "regulamente",
                    "title": "Metodologie burse",
                    "url": "https://uvt.ro/metodologie-burse.pdf",
                    "chunk_text": (
                        "Un student nu poate primi doua tipuri de burse simultan din aceeasi categorie, "
                        "prevazute la art. 2, alin. (1), lit. a)-e), dar are dreptul sa opteze "
                        "pentru cea cu valoare mai mare. "
                        "Bursele prevazute la art. 2 alin (4) pot fi cumulate cu alte burse. "
                        "Studentii care urmeaza concomitent doua programe de studii in institutii de stat "
                        "pot beneficia de burse de la bugetul de stat numai de la una dintre institutii."
                    ),
                }
            ],
            "confidence": "high",
            "confidence_score": 100,
            "confidence_reason": "Regula explicita.",
            "retrieval_backend": "qdrant",
        }

        answer, mode = app_module.build_deterministic_answer(retrieval_result)

        self.assertEqual(mode, "deterministic_policy")
        self.assertIn("Din sursa oficiala reiese ca", answer)
        self.assertIn("Un student nu poate primi doua tipuri de burse simultan", answer)
        self.assertIn("valoare mai mare", answer)
        self.assertIn("pot fi cumulate cu alte burse", answer)
        self.assertIn("numai de la una dintre institutii", answer)
        self.assertIn("https://uvt.ro/metodologie-burse.pdf", answer)

    def test_policy_extraction_is_not_scholarship_specific(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "regulamente",
                "is_policy_question": True,
                "corrected_question": "conditii cazare camin",
                "tokens": ["conditii", "cazare", "camin"],
                "expanded_tokens": ["conditii", "cazare", "camin", "eligibil"],
                "corrections": [],
            },
            "chunks": [
                {
                    "chunk_id": "cazare",
                    "faculty_id": "uvt",
                    "page_type": "regulamente",
                    "title": "Regulament cazare",
                    "url": "https://uvt.ro/regulament-cazare.pdf",
                    "chunk_text": (
                        "Studentii sunt eligibili pentru cazare daca au calitatea de student inmatriculat. "
                        "Cererea trebuie depusa in termenul stabilit prin calendarul oficial. "
                        "Locul de cazare se acorda numai daca dosarul este complet."
                    ),
                }
            ],
            "confidence": "high",
            "confidence_score": 90,
            "confidence_reason": "Reguli explicite.",
            "retrieval_backend": "qdrant",
        }

        answer, mode = app_module.build_deterministic_answer(retrieval_result)

        self.assertEqual(mode, "deterministic_policy")
        self.assertIn("Studentii sunt eligibili pentru cazare", answer)
        self.assertIn("Cererea trebuie depusa", answer)
        self.assertIn("Locul de cazare se acorda numai", answer)

    def test_policy_extraction_handles_procedural_portfolio_evidence(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "regulamente",
                "is_policy_question": True,
                "corrected_question": "depune dosar credite voluntariat",
                "tokens": ["depune", "dosar", "credite", "voluntariat"],
                "expanded_tokens": ["depune", "dosar", "credite", "voluntariat", "portofoliu", "formular"],
                "corrections": [],
            },
            "chunks": [
                {
                    "chunk_id": "voluntariat",
                    "faculty_id": "uvt",
                    "page_type": "regulamente",
                    "title": "Depunerea portofoliilor pentru credite de voluntariat",
                    "url": "https://uvt.ro/educatie/credite-voluntariat",
                    "chunk_text": (
                        "Depunerea portofoliilor pentru acordarea creditelor pentru implicarea in activitati "
                        "de voluntariat se poate realiza prin formularul oficial. "
                        "Portofoliul contine raport de activitate, copii ale diplomelor daca este cazul, "
                        "adeverinta care atesta minimum 60 ore si evaluare realizata de coordonator."
                    ),
                }
            ],
            "confidence": "high",
            "confidence_score": 92,
            "confidence_reason": "Reguli explicite.",
            "retrieval_backend": "qdrant",
        }

        answer, mode = app_module.build_deterministic_answer(retrieval_result)

        self.assertEqual(mode, "deterministic_policy")
        self.assertIn("Depunerea portofoliilor", answer)
        self.assertIn("formularul oficial", answer)
        self.assertIn("raport de activitate", answer)
        self.assertIn("adeverinta", answer)

    def test_live_verification_can_be_disabled_for_offline_runtime(self) -> None:
        retrieval_result = {
            "chunks": [{"url": "https://info.uvt.ro/orare", "chunk_text": "Orar"}],
        }

        with (
            patch.object(app_module, "LIVE_VERIFY_ENABLED", False),
            patch.object(app_module, "verify_pages", side_effect=AssertionError("Live fetch should not be called")),
        ):
            chunks, verified = app_module.live_verify_retrieval("orar", "info", retrieval_result, {"chunks": []})

        self.assertEqual(chunks, retrieval_result["chunks"])
        self.assertFalse(verified)

    def test_chat_uses_metadata_only_when_qdrant_is_ready(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "orar",
                "is_policy_question": False,
                "corrected_question": "orar",
                "tokens": ["orar"],
                "expanded_tokens": ["orar"],
                "corrections": [],
            },
            "chunks": [
                {
                    "chunk_id": "schedule",
                    "faculty_id": "info",
                    "page_type": "orar",
                    "title": "Orare",
                    "url": "https://info.uvt.ro/orare",
                    "chunk_text": "Orar oficial.",
                    "retrieval_score": 120,
                    "match_signals": ["schedule_exact_path"],
                }
            ],
            "confidence": "high",
            "confidence_score": 95,
            "confidence_reason": "OK",
            "retrieval_backend": "qdrant",
        }

        with (
            patch.object(app_module, "get_vector_index_status", return_value={"available": True, "points_count": 211506}),
            patch.object(app_module, "get_index_status", return_value={
                "schema_version": 2,
                "built_at": "test",
                "page_count": 29442,
                "chunk_count": 211506,
            }),
            patch.object(app_module, "load_index", side_effect=AssertionError("Full JSON should not be loaded")),
            patch.object(app_module, "rank_index", return_value=retrieval_result),
            patch.object(app_module, "live_verify_retrieval", return_value=(retrieval_result["chunks"], False)),
        ):
            response = self.client.post("/chat", json={"question": "Unde gasesc orarul?", "faculty_id": "info"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["retrieval_backend"], "qdrant")

    def test_chat_reports_startup_indexing_without_retrieval(self) -> None:
        original_indexing_state = app_module.get_indexing_state()
        self.addCleanup(lambda: app_module.set_indexing_state(**original_indexing_state))
        app_module.set_indexing_state(
            enabled=True,
            running=True,
            ready=False,
            phase="fetching",
            message="Descarc pagini oficiale.",
            progress=37,
        )

        with patch.object(app_module, "load_index", side_effect=AssertionError("Retrieval should wait for indexing")):
            response = self.client.post("/chat", json={"question": "Unde gasesc orarul?", "faculty_id": "info"})

        self.assertEqual(response.status_code, 503)
        payload = response.get_json()
        self.assertEqual(payload["retrieval_backend"], "indexing")
        self.assertEqual(payload["generation_mode"], "none")
        self.assertEqual(payload["indexing"]["progress"], 37)

    def test_startup_rebuild_skips_parent_debug_reloader_process(self) -> None:
        with (
            patch.object(app_module, "STARTUP_REBUILD_INDEX", True),
            patch.dict("os.environ", {"WERKZEUG_RUN_MAIN": "false"}, clear=False),
        ):
            self.assertFalse(app_module.should_run_startup_index_rebuild(debug=True))

        with (
            patch.object(app_module, "STARTUP_REBUILD_INDEX", True),
            patch.dict("os.environ", {"WERKZEUG_RUN_MAIN": "true"}, clear=False),
        ):
            self.assertTrue(app_module.should_run_startup_index_rebuild(debug=True))

    def test_feedback_accepts_malformed_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "feedback.jsonl"
            with patch.object(app_module, "LOG_FILE", log_file):
                response = self.client.post("/feedback", json=["bad"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
