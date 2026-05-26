from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from unittest.mock import patch

import retriever as retriever_module
from retriever import analyze_query, rank_lexical_index, rank_vector_index


def make_index(chunks: list[dict], built_at: str = "test") -> dict:
    return {
        "schema_version": 2,
        "built_at": built_at,
        "page_count": len({chunk["url"] for chunk in chunks}),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


class RetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query_analysis_patch = patch.object(retriever_module, "query_analysis_enabled", return_value=False)
        self.query_analysis_patch.start()
        self.addCleanup(self.query_analysis_patch.stop)

    def test_typo_correction_routes_orrarul_to_schedule_intent(self) -> None:
        analysis = analyze_query("Unde gasesc orrarul la info?")

        self.assertEqual(analysis.intent, "orar")
        self.assertIn("orar", analysis.corrected_question)

    def test_query_analysis_preserves_numeric_tokens(self) -> None:
        analysis = analyze_query("Poate un student sa primeasca 2 burse?")

        self.assertIn("2", analysis.tokens)

    def test_volunteering_credit_submission_is_not_admission_intent(self) -> None:
        analysis = analyze_query("Cum se depune dosarul pentru creditele de voluntariat?")

        self.assertEqual(analysis.intent, "regulamente")
        self.assertTrue(analysis.is_policy_question)
        self.assertIn("credite", analysis.tokens)
        self.assertIn("voluntariat", analysis.tokens)
        self.assertNotIn("admitere", analysis.expanded_tokens)
        self.assertEqual(analysis.page_type_preferences[:2], ("regulamente", "studenti"))

    def test_ollama_query_analysis_can_rewrite_and_expand_keywords(self) -> None:
        suggestion = {
            "corrected_question": "cum se depune portofoliul pentru credite voluntariat",
            "intent": "regulamente",
            "is_policy_question": True,
            "keywords": ["credite", "voluntariat", "portofoliu", "formular", "adeverinta"],
            "exclude_intents": ["admitere"],
        }

        with (
            patch.object(retriever_module, "query_analysis_enabled", return_value=True),
            patch.object(retriever_module, "ask_ollama_json", return_value=suggestion),
        ):
            analysis = analyze_query("cum depun dosaru pt voluntariat?")

        self.assertEqual(analysis.intent, "regulamente")
        self.assertTrue(analysis.is_policy_question)
        self.assertIn("portofoliu", analysis.expanded_tokens)
        self.assertIn("formular", analysis.expanded_tokens)
        self.assertIn("adeverinta", analysis.expanded_tokens)
        self.assertIn("ollama_query_rewrite", analysis.corrections)
        self.assertIn("ollama_keywords", analysis.corrections)
        self.assertIn("ollama_excluded:admitere", analysis.corrections)

    def test_ollama_query_analysis_rejects_untrusted_keywords_and_falls_back(self) -> None:
        suggestion = {
            "corrected_question": "pizza admitere extraterestru",
            "intent": "admitere",
            "is_policy_question": False,
            "keywords": ["pizza", "extraterestru", "voluntariat"],
        }

        with (
            patch.object(retriever_module, "query_analysis_enabled", return_value=True),
            patch.object(retriever_module, "ask_ollama_json", return_value=suggestion),
        ):
            analysis = analyze_query("Unde gasesc orarul?")

        self.assertEqual(analysis.intent, "orar")
        self.assertNotIn("pizza", analysis.expanded_tokens)
        self.assertNotIn("extraterestru", analysis.expanded_tokens)

        with (
            patch.object(retriever_module, "query_analysis_enabled", return_value=True),
            patch.object(retriever_module, "ask_ollama_json", side_effect=RuntimeError("ollama unavailable")),
        ):
            fallback = analyze_query("Unde gasesc orarul?")

        self.assertEqual(fallback.intent, "orar")
        self.assertNotIn("ollama_keywords", fallback.corrections)

    def test_volunteering_credit_query_prefers_volunteering_sources(self) -> None:
        index_document = make_index(
            [
                {
                    "chunk_id": "admission-payment",
                    "faculty_id": "uvt",
                    "page_type": "admitere",
                    "title": "Cuantum si modalitate de plata a taxelor | Admitere UVT",
                    "url": "https://admitere.uvt.ro/procesul-de-admitere/cuantum-modalitate-de-plata-a-taxelor",
                    "chunk_text": "Candidatul depune dosare electronice pentru programe de studii si achita taxe de admitere.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
                {
                    "chunk_id": "volunteering-portfolio",
                    "faculty_id": "uvt",
                    "page_type": "regulamente",
                    "title": "Depunerea portofoliilor pentru acordarea de credite pentru activitatea de voluntariat",
                    "url": "https://uvt.ro/educatie/depunerea-portofoliilor-credite-voluntariat",
                    "chunk_text": (
                        "Depunerea portofoliilor pentru acordarea creditelor pentru activitati de voluntariat "
                        "se realizeaza prin formular. Portofoliul contine raport de activitate, adeverinta si evaluare."
                    ),
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
            ],
            built_at="volunteering-credit-test",
        )

        result = rank_lexical_index(
            "Cum se depune dosarul pentru creditele de voluntariat?",
            index_document,
            "uvt",
            top_k=2,
        )

        self.assertEqual(result["chunks"][0]["chunk_id"], "volunteering-portfolio")
        self.assertIn("title_url_specific", " ".join(result["chunks"][0]["match_signals"]))

    def test_admission_query_prefers_stable_process_page_over_old_news(self) -> None:
        index_document = make_index(
            [
                {
                    "chunk_id": "old-news",
                    "faculty_id": "uvt",
                    "page_type": "admitere",
                    "title": "Admitere 2023 a inceput procesul de admitere la UVT",
                    "url": "https://admitere.uvt.ro/2023/06/19/admitere-2023-a-inceput-procesul-de-admitere-la-uvt",
                    "chunk_text": "Informatii despre admitere la UVT pentru candidati si inscriere.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
                {
                    "chunk_id": "stable-process",
                    "faculty_id": "uvt",
                    "page_type": "admitere",
                    "title": "Cum sa aplici - procesul de preinscriere online",
                    "url": "https://admitere.uvt.ro/procesul-de-admitere/cum-sa-aplici-procesul-de-preinscriere-online",
                    "chunk_text": "Informatii despre admitere la UVT, procesul de admitere, candidati si inscriere online.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
            ],
            built_at="admission-test",
        )

        result = rank_lexical_index("Unde gasesc informatii despre admitere?", index_document, "uvt", top_k=2)

        self.assertEqual(result["chunks"][0]["chunk_id"], "stable-process")
        self.assertIn("admission_process_path", result["chunks"][0]["match_signals"])
        self.assertIn("admission_dated_news_penalty", result["chunks"][1]["match_signals"])

    def test_vector_rank_does_not_prepare_full_index_when_semantic_hits_exist(self) -> None:
        semantic_hit = {
            "chunk_id": "schedule",
            "faculty_id": "info",
            "page_type": "orar",
            "title": "Orare",
            "url": "https://info.uvt.ro/orare",
            "chunk_text": "Orarul facultatii de informatica este publicat pe pagina oficiala.",
            "semantic_score": 0.92,
            "vector_filter": "selected_faculty_page_type",
            "last_indexed": "2026-01-01T00:00:00+00:00",
        }

        with (
            patch.object(retriever_module, "_retrieve_semantic_candidates", return_value=[semantic_hit]),
            patch.object(retriever_module, "prepare_index", side_effect=AssertionError("Full JSON index should not be prepared")),
            patch.object(retriever_module, "VECTOR_LEXICAL_BACKFILL_ENABLED", False),
        ):
            result = rank_vector_index("Unde gasesc orarul?", {"chunks": []}, "info", top_k=1)

        self.assertEqual(result["retrieval_backend"], "qdrant")
        self.assertEqual(result["chunks"][0]["chunk_id"], "schedule")

    def test_uvt_scholarship_policy_prefers_uvt_methodology_over_faculty_regulation(self) -> None:
        index_document = make_index(
            [
                {
                    "chunk_id": "feaa-regulation",
                    "faculty_id": "feaa",
                    "page_type": "regulamente",
                    "title": "Regulament de burse FEAA",
                    "url": "https://feaa.uvt.ro/regulament-burse.pdf",
                    "chunk_text": "Regulament burse. Art. 5 reguli de cumulare bursa studenti.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
                {
                    "chunk_id": "uvt-methodology",
                    "faculty_id": "uvt",
                    "page_type": "regulamente",
                    "title": "Metodologie privind acordarea burselor in UVT",
                    "url": "https://uvt.ro/metodologie-burse.pdf",
                    "chunk_text": "Metodologie burse. Art. 5 reguli de cumulare bursa studenti.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
            ],
            built_at="scholarship-policy-test",
        )

        result = rank_lexical_index(
            "Este posibil ca un student sa beneficieze de 2 burse?",
            index_document,
            "uvt",
            top_k=2,
        )

        self.assertEqual(result["chunks"][0]["chunk_id"], "uvt-methodology")
        self.assertIn("policy:uvt_scholarship_methodology", result["chunks"][0]["match_signals"])


if __name__ == "__main__":
    unittest.main()
