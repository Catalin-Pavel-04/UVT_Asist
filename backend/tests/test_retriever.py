from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from unittest.mock import patch

import rag.query_analysis as query_analysis_module
import rag.retrieval_service as retrieval_service_module
from rag.query_analysis import analyze_query
from rag.retrieval_service import rank_lexical_index, rank_vector_index, vector_search_limit_for_analysis


def make_index(chunks: list[dict], built_at: str = "test") -> dict:
    return {
        "schema_version": 2,
        "built_at": built_at,
        "page_count": len({chunk["url"] for chunk in chunks}),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


def make_query_analysis_suggestion(prompt: str) -> dict:
    question = prompt.split("Intrebare originala:", 1)[-1].lower()

    if "orrarul" in question or "orarul" in question or "orar" in question:
        return {
            "corrected_question": question.replace("orrarul", "orarul").strip(),
            "intent": "orar",
            "is_policy_question": False,
            "keywords": ["orar", "orare", "info"],
            "faculty_hint": "info" if "info" in question else "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "secretariat" in question or "contact" in question:
        return {
            "corrected_question": question.strip(),
            "intent": "contact",
            "is_policy_question": False,
            "keywords": ["contact", "secretariat", "uvt"],
            "faculty_hint": "info" if "informatica" in question or "info" in question else "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "admitere" in question:
        return {
            "corrected_question": question.strip(),
            "intent": "admitere",
            "is_policy_question": False,
            "keywords": ["admitere", "inscriere", "candidat"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "voluntariat" in question:
        return {
            "corrected_question": "cum se depune dosarul pentru credite voluntariat",
            "intent": "regulamente",
            "is_policy_question": True,
            "keywords": ["credite", "voluntariat", "portofoliu", "formular", "adeverinta"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "cazare" in question and ("orfan" in question or "acte" in question):
        return {
            "corrected_question": "depunere dosar cazare orfan parinte acte documente",
            "intent": "regulamente",
            "is_policy_question": True,
            "keywords": ["cazare", "dosar", "orfan", "parinte", "acte", "documente"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "monoparentala" in question or "acte trebuie" in question:
        return {
            "corrected_question": "familie monoparentala parinte financiar acte documente bursa sociala",
            "intent": "regulamente",
            "is_policy_question": True,
            "keywords": ["familie", "monoparentala", "parinte", "financiar", "acte", "documente", "burse", "social"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "burse" in question or "bursa" in question:
        return {
            "corrected_question": "student beneficia 2 burse cumulare",
            "intent": "regulamente",
            "is_policy_question": True,
            "keywords": ["student", "beneficia", "2", "burse", "cumulare"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "saptaman" in question or "sesiune" in question:
        return {
            "corrected_question": "unde vad saptamani de cursuri si sesiune",
            "intent": "studenti",
            "is_policy_question": False,
            "keywords": ["calendar", "structura", "saptamani", "sesiune", "cursuri"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "vacante" in question or "vacantele" in question:
        return {
            "corrected_question": "unde verific vacante din anul universitar",
            "intent": "studenti",
            "is_policy_question": False,
            "keywords": ["calendar", "structura", "vacante", "an", "universitar"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "semestr" in question:
        return {
            "corrected_question": "cand incepe semestru al doilea",
            "intent": "studenti",
            "is_policy_question": False,
            "keywords": ["calendar", "structura", "semestru", "cursuri"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }
    if "taxele" in question or "camine" in question:
        return {
            "corrected_question": "unde vad taxele pentru camine",
            "intent": "studenti",
            "is_policy_question": False,
            "keywords": ["taxe", "camine", "cazare"],
            "faculty_hint": "",
            "requires_clarification": False,
            "clarification_reason": "",
        }

    return {
        "corrected_question": question.strip(),
        "intent": "general",
        "is_policy_question": False,
        "keywords": [],
        "faculty_hint": "",
        "requires_clarification": False,
        "clarification_reason": "",
    }


class RetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        query_analysis_module._QUERY_REWRITE_CACHE.clear()
        self.query_analysis_patch = patch.object(query_analysis_module, "query_analysis_enabled", return_value=True)
        self.ollama_analysis_patch = patch.object(
            query_analysis_module,
            "ask_ollama_json",
            side_effect=lambda system_prompt, user_prompt, **kwargs: make_query_analysis_suggestion(user_prompt),
        )
        self.query_analysis_patch.start()
        self.ollama_analysis_patch.start()
        self.addCleanup(self.query_analysis_patch.stop)
        self.addCleanup(self.ollama_analysis_patch.stop)

    def test_ollama_query_analysis_routes_orrarul_to_schedule_intent(self) -> None:
        analysis = analyze_query("Unde gasesc orrarul la info?")

        self.assertEqual(analysis.intent, "orar")
        self.assertIn("orar", analysis.corrected_question)

    def test_navigation_queries_use_broader_vector_candidate_window(self) -> None:
        schedule_analysis = analyze_query("Unde este publicat orarul pentru studentii de la info?")
        contact_analysis = analyze_query("Unde gasesc secretariatul Facultatii de Informatica?")

        self.assertEqual(schedule_analysis.intent, "orar")
        self.assertEqual(contact_analysis.intent, "contact")
        self.assertGreaterEqual(vector_search_limit_for_analysis(schedule_analysis), 60)
        self.assertGreaterEqual(vector_search_limit_for_analysis(contact_analysis), 60)

    def test_uvt_contact_query_prefers_central_contact_over_localized_page(self) -> None:
        index_document = make_index(
            [
                {
                    "chunk_id": "localized",
                    "faculty_id": "uvt",
                    "page_type": "studenti",
                    "title": "Affectation de materiel informatique destine aux etudiants de l'UVT",
                    "url": "https://uvt.ro/fr/educatie/2024/01/atribuirea-dispozitivelor-it-destinate-studentilor-uvt",
                    "chunk_text": "Contact UVT pentru studenti si informatii administrative.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
                {
                    "chunk_id": "contact",
                    "faculty_id": "uvt",
                    "page_type": "contact",
                    "title": "Contact - UVT",
                    "url": "https://uvt.ro/contact",
                    "chunk_text": "Pagina oficiala de contact a Universitatii de Vest din Timisoara.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
            ],
            built_at="contact-test",
        )

        result = rank_lexical_index("Unde gasesc datele de contact UVT?", index_document, "uvt", top_k=2)

        self.assertEqual(result["chunks"][0]["chunk_id"], "contact")
        self.assertIn("contact_exact_path", result["chunks"][0]["match_signals"])
        self.assertNotIn("localized", [chunk["chunk_id"] for chunk in result["chunks"][:1]])

    def test_vector_rank_injects_canonical_uvt_contact_source(self) -> None:
        contact_chunk = {
            "chunk_id": "contact",
            "faculty_id": "uvt",
            "page_type": "contact",
            "title": "Contact - UVT",
            "url": "https://uvt.ro/contact",
            "chunk_text": "Pagina oficiala de contact a Universitatii de Vest din Timisoara.",
            "last_indexed": "2026-01-01T00:00:00+00:00",
        }
        bad_semantic_hit = {
            "chunk_id": "contract",
            "faculty_id": "uvt",
            "page_type": "studenti",
            "title": "Contract de inchiriere",
            "url": "https://uvt.ro/wp-content/uploads/sites/3/2025/07/Contract-de-inchiriere-2025-2026-pentru-site.pdf",
            "chunk_text": "Contract pentru cazare.",
            "semantic_score": 0.91,
            "vector_filter": "uvt",
            "last_indexed": "2026-01-01T00:00:00+00:00",
        }

        with patch.object(retrieval_service_module, "_retrieve_semantic_candidates", return_value=[bad_semantic_hit]):
            result = rank_vector_index(
                "Unde gasesc datele de contact UVT?",
                make_index([contact_chunk], built_at="canonical-contact-test"),
                "uvt",
                top_k=2,
            )

        self.assertEqual(result["chunks"][0]["chunk_id"], "contact")
        self.assertIn("canonical_contact", result["chunks"][0]["match_signals"])

    def test_query_analysis_preserves_numeric_tokens(self) -> None:
        analysis = analyze_query("Poate un student sa primeasca 2 burse?")

        self.assertIn("2", analysis.tokens)

    def test_social_document_query_does_not_rewrite_doar_to_dosar(self) -> None:
        analysis = analyze_query(
            "Daca provin dintr-o familie monoparentala si doar un parinte ma ajuta financiar, ce acte trebuie?"
        )

        self.assertNotIn("doar->dosar", analysis.corrections)
        self.assertTrue(analysis.is_policy_question)
        self.assertIn(analysis.intent, {"burse", "regulamente"})
        self.assertIn("burse", analysis.expanded_tokens)
        self.assertIn("documente", analysis.expanded_tokens)
        self.assertNotIn("cumulare", analysis.expanded_tokens)

        embedding_texts = retrieval_service_module.build_query_embedding_texts(
            "Daca provin dintr-o familie monoparentala si doar un parinte ma ajuta financiar, ce acte trebuie?",
            analysis,
        )
        self.assertGreater(len(embedding_texts), 1)
        self.assertIn("documentele necesare", embedding_texts[1].lower())

    def test_housing_social_dossier_query_is_policy_scoped(self) -> None:
        analysis = analyze_query(
            "Vreau sa imi depun dosarul pentru cazare, dar sunt orfan de un parinte, ce acte am nevoie?"
        )

        self.assertEqual(analysis.intent, "regulamente")
        self.assertTrue(analysis.is_policy_question)
        self.assertEqual(analysis.page_type_preferences[:2], ("regulamente", "studenti"))
        self.assertIn("cazare", analysis.expanded_tokens)
        self.assertIn("documente", analysis.expanded_tokens)

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
            patch.object(query_analysis_module, "query_analysis_enabled", return_value=True),
            patch.object(query_analysis_module, "ask_ollama_json", return_value=suggestion),
        ):
            analysis = analyze_query("cum depun dosaru pt voluntariat?")

        self.assertEqual(analysis.intent, "regulamente")
        self.assertTrue(analysis.is_policy_question)
        self.assertIn("portofoliu", analysis.expanded_tokens)
        self.assertIn("formular", analysis.expanded_tokens)
        self.assertIn("adeverinta", analysis.expanded_tokens)
        self.assertIn("ollama_query_rewrite", analysis.corrections)
        self.assertIn("ollama_keywords", analysis.corrections)

    def test_ollama_query_analysis_invalid_shape_falls_back_raw(self) -> None:
        with (
            patch.object(query_analysis_module, "query_analysis_enabled", return_value=True),
            patch.object(query_analysis_module, "ask_ollama_json", return_value=["not", "json", "object"]),
        ):
            analysis = analyze_query("Unde gasesc orarul?")

        self.assertEqual(analysis.intent, "general")
        self.assertEqual(analysis.rewrite_source, "raw_fallback")
        self.assertEqual(analysis.corrected_question, "unde gasesc orarul?")

        query_analysis_module._QUERY_REWRITE_CACHE.clear()
        with (
            patch.object(query_analysis_module, "query_analysis_enabled", return_value=True),
            patch.object(query_analysis_module, "ask_ollama_json", side_effect=RuntimeError("ollama unavailable")),
        ):
            fallback = analyze_query("Unde gasesc orarul?")

        self.assertEqual(fallback.intent, "general")
        self.assertEqual(fallback.rewrite_source, "raw_fallback")
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

    def test_academic_calendar_query_prefers_year_structure_page(self) -> None:
        index_document = make_index(
            [
                {
                    "chunk_id": "old-course-news",
                    "faculty_id": "uvt",
                    "page_type": "studenti",
                    "title": "ProLitRom cursuri de perfectionare",
                    "url": "https://uvt.ro/blog/2021/02/prolitrom-cursuri-de-perfectionare",
                    "chunk_text": "Cursuri de perfectionare pentru profesori.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
                {
                    "chunk_id": "calendar",
                    "faculty_id": "uvt",
                    "page_type": "studenti",
                    "title": "Structura anului universitar",
                    "url": "https://uvt.ro/educatie/info-studenti-proces-educational/structura-anului-universitar",
                    "chunk_text": "Structura anului universitar contine saptamanile de cursuri, sesiune si vacante.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
            ],
            built_at="calendar-test",
        )

        result = rank_lexical_index("Unde vad saptamanile de cursuri si sesiune?", index_document, "uvt", top_k=2)

        self.assertEqual(result["chunks"][0]["chunk_id"], "calendar")
        self.assertIn("academic_calendar", result["chunks"][0]["match_signals"])

    def test_calendar_queries_use_targeted_vector_search_text(self) -> None:
        question = "Unde verific vacantele din anul universitar?"
        analysis = analyze_query(question)

        self.assertGreaterEqual(vector_search_limit_for_analysis(analysis), 80)
        embedding_texts = retrieval_service_module.build_query_embedding_texts(question, analysis)

        self.assertTrue(any("Structura anului universitar" in text for text in embedding_texts[1:]))

    def test_housing_queries_do_not_get_calendar_targeted_search_text(self) -> None:
        question = "Unde vad taxele pentru camine?"
        analysis = analyze_query(question)
        embedding_texts = retrieval_service_module.build_query_embedding_texts(question, analysis)

        self.assertFalse(any("Structura anului universitar" in text for text in embedding_texts[1:]))

    def test_semester_query_prefers_stable_calendar_over_old_news(self) -> None:
        index_document = make_index(
            [
                {
                    "chunk_id": "old-semester-news",
                    "faculty_id": "uvt",
                    "page_type": "studenti",
                    "title": "Semestrul al doilea incepe in regim diferentiat, la UVT",
                    "url": "https://uvt.ro/blog/semestrul-al-doilea-incepe-in-regim-diferentiat-la-uvt",
                    "chunk_text": "Semestrul al doilea incepe in regim diferentiat conform unei decizii din 2021.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
                {
                    "chunk_id": "calendar",
                    "faculty_id": "uvt",
                    "page_type": "studenti",
                    "title": "Structura anului universitar",
                    "url": "https://uvt.ro/educatie/info-studenti-proces-educational/structura-anului-universitar",
                    "chunk_text": "Structura anului universitar contine semestrul al doilea, cursuri, sesiuni si vacante.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
            ],
            built_at="semester-calendar-test",
        )

        result = rank_lexical_index("Cand incepe semestrul al doilea?", index_document, "uvt", top_k=2)

        self.assertEqual(result["chunks"][0]["chunk_id"], "calendar")
        self.assertIn("academic_calendar", result["chunks"][0]["match_signals"])

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
            patch.object(retrieval_service_module, "_retrieve_semantic_candidates", return_value=[semantic_hit]),
            patch.object(
                retrieval_service_module,
                "prepare_index",
                side_effect=AssertionError("Full JSON index should not be prepared"),
            ),
            patch.object(retrieval_service_module, "VECTOR_LEXICAL_BACKFILL_ENABLED", False),
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

    def test_social_document_query_prefers_scholarship_methodology_over_generic_financial_aid(self) -> None:
        index_document = make_index(
            [
                {
                    "chunk_id": "euro-200",
                    "faculty_id": "uvt",
                    "page_type": "studenti",
                    "title": "Programul Euro 200 privind acordarea unui ajutor financiar studentilor",
                    "url": "https://uvt.ro/educatie/programul-euro-200",
                    "chunk_text": "Ajutor financiar pentru achizitionarea de calculatoare. Studentii depun cerere si acte.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
                {
                    "chunk_id": "social-scholarship-docs",
                    "faculty_id": "uvt",
                    "page_type": "regulamente",
                    "title": "Metodologie privind acordarea burselor",
                    "url": "https://uvt.ro/metodologie-burse.pdf",
                    "chunk_text": (
                        "Burse pentru sprijin social. Sunt eligibili studentii orfani si studentii care provin "
                        "din familii monoparentale. Anexa nr. 2 documentele necesare pentru bursele sociale: "
                        "cerere, documente justificative privind veniturile, certificat de divort sau hotarare judecatoreasca."
                    ),
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
            ],
            built_at="social-documents-test",
        )

        result = rank_lexical_index(
            "Daca provin dintr-o familie monoparentala si doar un parinte ma ajuta financiar, ce acte trebuie?",
            index_document,
            "uvt",
            top_k=2,
        )

        self.assertEqual(result["chunks"][0]["chunk_id"], "social-scholarship-docs")
        self.assertIn("policy:social_documents", result["chunks"][0]["match_signals"])
        self.assertIn("policy:social_scholarship_methodology", result["chunks"][0]["match_signals"])

    def test_housing_orphan_query_prefers_housing_regulation(self) -> None:
        index_document = make_index(
            [
                {
                    "chunk_id": "housing-page",
                    "faculty_id": "uvt",
                    "page_type": "studenti",
                    "title": "Cazare in caminele UVT",
                    "url": "https://uvt.ro/educatie/campus-uvt/cazare-in-caminele-uvt",
                    "chunk_text": "Informatii generale despre cazare in caminele UVT.",
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
                {
                    "chunk_id": "housing-regulation",
                    "faculty_id": "uvt",
                    "page_type": "regulamente",
                    "title": "Regulament privind cazarea in caminele UVT",
                    "url": "https://uvt.ro/regulament-cazare.pdf",
                    "chunk_text": (
                        "Criterii sociale pentru cazare. Studentii orfani de un parinte primesc punctaj "
                        "la situatia familiala. Dosarul de cazare include cererea de cazare si documente "
                        "justificative care dovedesc cazul social."
                    ),
                    "last_indexed": "2026-01-01T00:00:00+00:00",
                },
            ],
            built_at="housing-documents-test",
        )

        result = rank_lexical_index(
            "Vreau sa imi depun dosarul pentru cazare, dar sunt orfan de un parinte, ce acte am nevoie?",
            index_document,
            "uvt",
            top_k=2,
        )

        self.assertEqual(result["chunks"][0]["chunk_id"], "housing-regulation")
        self.assertIn("policy:housing_documents", result["chunks"][0]["match_signals"])


if __name__ == "__main__":
    unittest.main()
