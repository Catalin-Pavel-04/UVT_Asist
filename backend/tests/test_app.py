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

    def test_generation_skips_only_when_no_chunks_exist(self) -> None:
        self.assertTrue(app_module.should_skip_generation({"chunks": []}))
        self.assertFalse(app_module.should_skip_generation({
            "chunks": [{"url": "https://uvt.ro", "chunk_text": "Fragment oficial."}],
            "confidence": "low",
            "confidence_score": 10,
        }))

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
            patch.object(app_module, "ask_ollama_json", side_effect=AssertionError("LLM should not be called")),
        ):
            response = self.client.post(
                "/chat",
                json={"question": "intrebare imposibila despre document local", "faculty_id": "uvt"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["generation_mode"], "fallback_low_evidence")
        self.assertEqual(payload["sources"], [])
        self.assertFalse(payload["evidence"]["answerable"])

    def test_low_confidence_with_sources_still_uses_ollama(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "general",
                "is_policy_question": False,
                "corrected_question": "taxa camin",
                "tokens": ["taxa", "camin"],
                "expanded_tokens": ["taxa", "camin"],
                "corrections": [],
            },
            "chunks": [
                {
                    "chunk_id": "general",
                    "faculty_id": "uvt",
                    "page_type": "general",
                    "title": "Pagina generala UVT",
                    "url": "https://uvt.ro/",
                    "chunk_text": "Pagina generala a universitatii.",
                    "retrieval_score": 20,
                    "match_signals": [],
                }
            ],
            "confidence": "low",
            "confidence_score": 30,
            "confidence_reason": "Dovezi prea generale.",
            "retrieval_backend": "qdrant",
        }

        with (
            patch.object(app_module, "load_index", return_value={"built_at": "test", "chunks": []}),
            patch.object(app_module, "get_vector_index_status", return_value={"points_count": 1}),
            patch.object(app_module, "rank_index", return_value=retrieval_result),
            patch.object(app_module, "live_verify_retrieval", return_value=(retrieval_result["chunks"], False)),
            patch.object(
                app_module,
                "ask_ollama_json",
                return_value={"answer": "Sursele recuperate sunt prea generale pentru un raspuns sigur."},
            ) as ask_ollama,
        ):
            response = self.client.post("/chat", json={"question": "cat e taxa de camin?", "faculty_id": "uvt"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["generation_mode"], "ollama")
        self.assertEqual(payload["answer"], "Sursele recuperate sunt prea generale pentru un raspuns sigur.")
        ask_ollama.assert_called_once()

    def test_central_uvt_contact_does_not_require_faculty_clarification(self) -> None:
        faculty = {"id": "uvt", "name": "UVT"}

        self.assertFalse(app_module.needs_faculty_clarification(
            faculty,
            {"analysis": {"intent": "contact", "corrected_question": "unde gasesc datele de contact uvt"}},
        ))
        self.assertTrue(app_module.needs_faculty_clarification(
            faculty,
            {"analysis": {"intent": "contact", "corrected_question": "unde gasesc secretariatul"}},
        ))

    def test_central_uvt_contact_source_is_prioritized(self) -> None:
        retrieval_result = {
            "analysis": {"intent": "contact", "corrected_question": "unde gasesc datele de contact uvt"},
            "chunks": [
                {
                    "chunk_id": "contract",
                    "faculty_id": "uvt",
                    "page_type": "studenti",
                    "title": "Contract de inchiriere",
                    "url": "https://uvt.ro/wp-content/uploads/sites/3/2025/07/Contract-de-inchiriere.pdf",
                    "chunk_text": "Contract pentru cazare.",
                    "retrieval_score": 80,
                    "match_signals": [],
                }
            ],
            "confidence": "high",
            "confidence_score": 90,
            "confidence_reason": "Test.",
            "retrieval_backend": "qdrant",
        }
        contact_chunk = {
            "chunk_id": "contact",
            "faculty_id": "uvt",
            "page_type": "contact",
            "title": "Contact - UVT",
            "url": "https://uvt.ro/contact",
            "chunk_text": "Pagina oficiala de contact a Universitatii de Vest din Timisoara.",
        }

        with patch.object(app_module, "load_index", return_value={"chunks": [contact_chunk]}):
            result = app_module.ensure_canonical_uvt_contact_source(
                "Unde gasesc datele de contact UVT?",
                {"id": "uvt", "name": "UVT"},
                retrieval_result,
            )

        self.assertEqual(result["chunks"][0]["url"], "https://uvt.ro/contact")
        self.assertIn("canonical_contact", result["chunks"][0]["match_signals"])

    def test_housing_calendar_navigation_topic_stays_housing(self) -> None:
        topic = app_module.source_navigation_topic(
            "Unde gasesc calendarul procesului de cazare?",
            {"analysis": {"intent": "studenti"}},
        )

        self.assertEqual(topic, "cazare")

    def test_housing_social_navigation_topic_mentions_social_criteria(self) -> None:
        topic = app_module.source_navigation_topic(
            "Unde verific criteriile sociale pentru cazare?",
            {"analysis": {"intent": "studenti"}},
        )

        self.assertEqual(topic, "criteriile sociale pentru cazare")

    def test_policy_source_navigation_question_can_use_local_answer(self) -> None:
        retrieval_result = {
            "analysis": {"intent": "regulamente", "is_policy_question": True},
            "chunks": [{"url": "https://uvt.ro/regulament", "title": "Regulament", "chunk_text": "Text"}],
            "confidence": "high",
        }

        self.assertTrue(app_module.should_use_source_navigation_answer(
            "Ce document oficial explica procedurile pentru studenti?",
            retrieval_result,
        ))
        self.assertTrue(app_module.should_use_source_navigation_answer(
            "Unde gasesc metodologia de finalizare a studiilor?",
            retrieval_result,
        ))

    def test_policy_navigation_topic_mentions_regulations(self) -> None:
        topic = app_module.source_navigation_topic(
            "Unde sunt publicate hotararile sau regulamentele UVT?",
            {"analysis": {"intent": "regulamente"}},
        )

        self.assertIn("regulament", topic)

    def test_local_fallback_lists_sources_without_content_analysis(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "general",
                "is_policy_question": False,
                "corrected_question": "metodologie burse",
                "tokens": ["metodologie", "burse"],
                "expanded_tokens": ["metodologie", "burse", "document"],
                "corrections": [],
            },
            "chunks": [
                {
                    "chunk_id": "burse",
                    "faculty_id": "info",
                    "page_type": "studenti",
                    "title": "Burse - Facultatea de Informatica",
                    "url": "https://info.uvt.ro/burse",
                    "chunk_text": (
                        "Burse Informatii relevante privind procesul de acordare a burselor. "
                        "Metodologia privind acordarea burselor pentru anul universitar curent poate fi accesata aici."
                    ),
                }
            ],
            "confidence": "medium",
            "confidence_score": 60,
            "confidence_reason": "Exista surse oficiale relevante.",
            "retrieval_backend": "qdrant",
        }

        answer = app_module.build_local_fallback_answer(retrieval_result)

        self.assertIn("analiza informatiei este rezervata pentru Ollama", answer)
        self.assertIn("\"Burse - Facultatea de Informatica\" - https://info.uvt.ro/burse", answer)
        self.assertNotIn("Metodologia privind acordarea burselor", answer)

    def test_low_evidence_with_sources_still_cites_nearest_sources(self) -> None:
        retrieval_result = {
            "analysis": {
                "intent": "general",
                "is_policy_question": False,
                "corrected_question": "taxa camin",
                "tokens": ["taxa", "camin"],
                "expanded_tokens": ["taxa", "camin"],
                "corrections": [],
            },
            "chunks": [
                {
                    "chunk_id": "general",
                    "faculty_id": "uvt",
                    "page_type": "general",
                    "title": "Pagina generala UVT",
                    "url": "https://uvt.ro/",
                    "chunk_text": "Pagina generala a universitatii.",
                }
            ],
            "confidence": "low",
            "confidence_score": 30,
            "confidence_reason": "Dovezi prea generale.",
            "retrieval_backend": "qdrant",
        }

        answer = app_module.build_local_fallback_answer(retrieval_result)

        self.assertIn("Backend-ul a gasit doar dovezi partiale", answer)
        self.assertIn("\"Pagina generala UVT\" - https://uvt.ro/", answer)

    def test_navigation_question_uses_ollama_with_backend_sources(self) -> None:
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
            patch.object(app_module, "ask_ollama_json", side_effect=AssertionError("Navigation answer should be local")),
        ):
            response = self.client.post("/chat", json={"question": "Unde gasesc orarul?", "faculty_id": "info"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["generation_mode"], "local_source_navigation")
        self.assertTrue(payload["evidence"]["answerable"])
        self.assertEqual(payload["evidence"]["top_source"]["url"], "https://info.uvt.ro/orare")
        self.assertIn("orar", payload["answer"].lower())
        self.assertIn("https://info.uvt.ro/orare", payload["answer"])

    def test_unsupported_future_or_personal_question_skips_retrieval(self) -> None:
        with patch.object(app_module, "rank_index", side_effect=AssertionError("Unsupported question should not retrieve")):
            for question in (
                "Care va fi media minima de admitere de anul viitor?",
                "Ce bursa voi primi personal luna viitoare?",
            ):
                with self.subTest(question=question):
                    response = self.client.post(
                        "/chat",
                        json={"question": question, "faculty_id": "uvt"},
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.get_json()
                    self.assertEqual(payload["confidence"], "low")
                    self.assertEqual(payload["retrieval_backend"], "unsupported_guard")
                    self.assertFalse(payload["evidence"]["answerable"])
                    self.assertIn("Sursele oficiale disponibile nu sunt suficiente", payload["answer"])

    def test_bad_generation_is_repaired_with_ollama_before_fallback(self) -> None:
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
                    "match_signals": ["schedule_exact_path"],
                }
            ],
            "confidence": "high",
            "confidence_score": 95,
            "confidence_reason": "Potrivire directa.",
            "retrieval_backend": "qdrant",
        }

        with (
            patch.object(app_module, "load_index", return_value={"built_at": "test", "chunks": []}),
            patch.object(app_module, "get_vector_index_status", return_value={"points_count": 1}),
            patch.object(app_module, "rank_index", return_value=retrieval_result),
            patch.object(app_module, "live_verify_retrieval", return_value=(retrieval_result["chunks"], False)),
            patch.object(
                app_module,
                "ask_ollama_json",
                side_effect=[
                    {"answer": "According to Source 1, orarul este disponibil in retrieved context."},
                    {"answer": "Orarul este publicat pe pagina oficiala \"Orare - Facultatea de Informatica\" - https://info.uvt.ro/orare."},
                ],
            ) as ask_ollama,
        ):
            response = self.client.post(
                "/chat",
                json={"question": "Ce informatii sunt publicate pe pagina de orar?", "faculty_id": "info"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["generation_mode"], "ollama_repair")
        self.assertIn("https://info.uvt.ro/orare", payload["answer"])
        self.assertNotIn("Source 1", payload["answer"])
        self.assertEqual(ask_ollama.call_count, 2)
        repair_prompt = ask_ollama.call_args.args[1]
        self.assertIn("Previous draft that must be repaired", repair_prompt)
        self.assertIn("Orare - Facultatea de Informatica", repair_prompt)

    def test_policy_question_uses_ollama_with_retrieved_evidence(self) -> None:
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

        with (
            patch.object(app_module, "load_index", return_value={"built_at": "test", "chunks": []}),
            patch.object(app_module, "get_vector_index_status", return_value={"points_count": 1}),
            patch.object(app_module, "rank_index", return_value=retrieval_result),
            patch.object(app_module, "live_verify_retrieval", return_value=(retrieval_result["chunks"], False)),
            patch.object(
                app_module,
                "ask_ollama_json",
                return_value=(
                    {
                        "answer": (
                            "Conform metodologiei, bursele din aceeasi categorie nu se cumuleaza, "
                            "iar anumite burse pot fi cumulate cu alte burse. Sursa: Metodologie burse - https://uvt.ro/metodologie-burse.pdf."
                        )
                    }
                ),
            ) as ask_ollama,
        ):
            response = self.client.post(
                "/chat",
                json={"question": "Este posibil ca un student sa beneficieze de 2 burse?", "faculty_id": "uvt"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["generation_mode"], "ollama")
        self.assertIn("Metodologie burse", payload["answer"])
        ask_ollama.assert_called_once()
        prompt = ask_ollama.call_args.args[1]
        self.assertIn("Un student nu poate primi doua tipuri de burse simultan", prompt)
        self.assertIn("Bursele prevazute la art. 2 alin (4) pot fi cumulate", prompt)
        self.assertIn("https://uvt.ro/metodologie-burse.pdf", prompt)

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

    def test_live_verification_deep_fetches_policy_documents(self) -> None:
        retrieval_result = {
            "analysis": {"intent": "regulamente", "is_policy_question": True},
            "chunks": [{"url": "https://uvt.ro/metodologie-burse.pdf", "chunk_text": "Burse"}],
        }

        with patch.object(app_module, "verify_pages", return_value=[]) as verify_pages:
            chunks, verified = app_module.live_verify_retrieval("ce acte trebuie", "uvt", retrieval_result, {"chunks": []})

        self.assertEqual(chunks, retrieval_result["chunks"])
        self.assertFalse(verified)
        self.assertTrue(verify_pages.call_args.kwargs["index_mode"])

    def test_merge_ranked_chunks_preserves_multiple_chunks_from_same_primary_url(self) -> None:
        primary_chunks = [
            {"chunk_id": "old-1", "url": "https://uvt.ro/doc.pdf", "title": "Doc", "chunk_text": "old one"},
            {"chunk_id": "old-2", "url": "https://uvt.ro/doc.pdf", "title": "Doc", "chunk_text": "old two"},
        ]
        verified_chunks = [
            {
                "chunk_id": "new-1",
                "url": "https://uvt.ro/doc.pdf",
                "title": "Doc verificat",
                "chunk_text": "documentele necesare",
                "retrieval_score": 90,
            },
            {
                "chunk_id": "new-2",
                "url": "https://uvt.ro/doc.pdf",
                "title": "Doc verificat",
                "chunk_text": "certificat de divort",
                "retrieval_score": 80,
            },
        ]

        merged = app_module.merge_ranked_chunks(primary_chunks, verified_chunks)

        self.assertEqual(len(merged), 2)
        self.assertEqual([chunk["chunk_text"] for chunk in merged], ["documentele necesare", "certificat de divort"])
        self.assertTrue(all(chunk["verified"] for chunk in merged))

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
            patch.object(app_module, "ask_ollama_json", return_value={"answer": "Orar oficial."}),
        ):
            response = self.client.post("/chat", json={"question": "Unde gasesc orarul?", "faculty_id": "info"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["retrieval_backend"], "qdrant")

    def test_chat_retries_full_json_when_metadata_vector_search_has_no_chunks(self) -> None:
        empty_vector_result = {
            "analysis": {
                "intent": "orar",
                "is_policy_question": False,
                "corrected_question": "orar",
                "tokens": ["orar"],
                "expanded_tokens": ["orar"],
                "corrections": [],
            },
            "chunks": [],
            "confidence": "low",
            "confidence_score": 10,
            "confidence_reason": "Qdrant nu a returnat fragmente.",
            "retrieval_backend": "qdrant",
        }
        lexical_result = {
            "analysis": empty_vector_result["analysis"],
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
            "confidence_reason": "Potrivire lexicala.",
            "retrieval_backend": "local_json_lexical",
        }
        full_index = {
            "schema_version": 2,
            "built_at": "test",
            "page_count": 1,
            "chunk_count": 1,
            "chunks": lexical_result["chunks"],
        }

        with (
            patch.object(app_module, "get_vector_index_status", return_value={"available": True, "points_count": 1}),
            patch.object(app_module, "get_index_status", return_value={
                "schema_version": 2,
                "built_at": "test",
                "page_count": 1,
                "chunk_count": 1,
            }),
            patch.object(app_module, "rank_index", return_value=empty_vector_result),
            patch.object(app_module, "load_index", return_value=full_index) as load_index,
            patch.object(app_module, "rank_lexical_index", return_value=lexical_result) as rank_lexical,
            patch.object(app_module, "live_verify_retrieval", return_value=(lexical_result["chunks"], False)),
            patch.object(app_module, "ask_ollama_json", return_value={"answer": "Orar oficial."}),
        ):
            response = self.client.post("/chat", json={"question": "Unde gasesc orarul?", "faculty_id": "info"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["retrieval_backend"], "local_json_fallback")
        self.assertEqual(payload["evidence"]["top_source"]["url"], "https://info.uvt.ro/orare")
        load_index.assert_called_once()
        rank_lexical.assert_called_once()

    def test_cache_key_changes_with_chat_cache_version(self) -> None:
        with patch.object(app_module, "CHAT_CACHE_VERSION", "contract-a"):
            first_key = app_module.build_cache_key("uvt", "orar", [], "built", 1)
        with patch.object(app_module, "CHAT_CACHE_VERSION", "contract-b"):
            second_key = app_module.build_cache_key("uvt", "orar", [], "built", 1)

        self.assertNotEqual(first_key, second_key)

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
