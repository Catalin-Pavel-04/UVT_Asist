from __future__ import annotations

# Compatibility facade: existing scripts and services import from this module.
from rag import query_analysis as _query_analysis_module
from rag import retrieval_service as _retrieval_service_module
from rag.confidence import compute_confidence
from rag.constants import *  # noqa: F401,F403
from rag.intent_detection import (  # noqa: F401
    _has_document_request,
    _has_housing_context,
    _has_social_context,
    _is_housing_document_question,
    _is_social_document_question,
    detect_intent,
    detect_policy_question,
    is_academic_calendar_query,
    is_central_uvt_contact_query,
    is_volunteering_credit_query,
)
from rag.query_analysis import (  # noqa: F401
    QueryAnalysis,
    _build_ollama_query_analysis_prompt,
    _query_analysis_allowed_token,
    _score_intents,
    _validated_corrected_question,
    _validated_query_analysis_intents,
    _validated_query_analysis_tokens,
    analyze_query,
    analyze_query_deterministic,
    build_page_type_preferences,
    expand_query_tokens,
    merge_ollama_query_analysis,
    query_analysis_enabled,
    request_ollama_query_analysis,
)
from rag.ranking.faculty import _faculty_score  # noqa: F401
from rag.ranking.lexical import (  # noqa: F401
    _contains_any,
    _contains_token,
    _counter,
    _field_overlap_score,
    _lexical_score,
)
from rag.ranking.page_type import (  # noqa: F401
    _academic_year_starts,
    _current_academic_year_start,
    _is_document_url,
    _is_homepage,
    _page_type_score,
    _specific_page_score,
    _upload_year_from_path,
    _url_path,
    _url_slug_tokens,
)
from rag.ranking.policy import _is_institutional_policy_document, _policy_score  # noqa: F401
from rag.retrieval_service import (  # noqa: F401
    _candidate_allowed,
    _canonical_central_contact_candidates,
    _merge_scored_candidates,
    _merge_semantic_hits,
    _prefer_academic_calendar_candidates,
    _prefer_policy_candidates,
    _prefer_selected_scope_candidates,
    _prepare_chunk,
    _retrieve_semantic_candidates,
    _score_lexical_backfill_candidates,
    _score_semantic_candidates,
    _vector_search_passes,
    build_query_embedding_text,
    build_query_embedding_texts,
    max_chunks_per_url_for_analysis,
    prepare_index,
    rank_index,
    rank_lexical_index,
    rank_runtime_chunks,
    rank_vector_index,
    score_chunk_candidate,
    select_diverse_chunks,
    vector_search_limit_for_analysis,
)
from rag.text_normalization import (  # noqa: F401
    _canonical_token,
    _clean_for_tokens,
    correct_query_terms,
    normalize,
    tokenize,
)
from ollama_client import ask_ollama_json  # noqa: F401

_ANALYZE_QUERY_IMPL = _query_analysis_module.analyze_query
_RANK_INDEX_IMPL = _retrieval_service_module.rank_index
_RANK_LEXICAL_INDEX_IMPL = _retrieval_service_module.rank_lexical_index
_RANK_RUNTIME_CHUNKS_IMPL = _retrieval_service_module.rank_runtime_chunks
_RANK_VECTOR_INDEX_IMPL = _retrieval_service_module.rank_vector_index


def _sync_query_analysis_overrides() -> None:
    _query_analysis_module.ask_ollama_json = ask_ollama_json
    _query_analysis_module.query_analysis_enabled = query_analysis_enabled


def _sync_retrieval_overrides() -> None:
    _sync_query_analysis_overrides()
    _retrieval_service_module.VECTOR_LEXICAL_BACKFILL_ENABLED = VECTOR_LEXICAL_BACKFILL_ENABLED
    _retrieval_service_module._retrieve_semantic_candidates = _retrieve_semantic_candidates
    _retrieval_service_module.analyze_query = analyze_query
    _retrieval_service_module.prepare_index = prepare_index


def analyze_query(question: str) -> QueryAnalysis:
    _sync_query_analysis_overrides()
    return _ANALYZE_QUERY_IMPL(question)


def rank_vector_index(question: str, index_document: dict, selected_faculty: str, top_k: int = 6) -> dict:
    _sync_retrieval_overrides()
    return _RANK_VECTOR_INDEX_IMPL(question, index_document, selected_faculty, top_k=top_k)


def rank_lexical_index(question: str, index_document: dict, selected_faculty: str, top_k: int = 6) -> dict:
    _sync_retrieval_overrides()
    return _RANK_LEXICAL_INDEX_IMPL(question, index_document, selected_faculty, top_k=top_k)


def rank_index(question: str, index_document: dict, selected_faculty: str, top_k: int = 6) -> dict:
    _sync_retrieval_overrides()
    return _RANK_INDEX_IMPL(question, index_document, selected_faculty, top_k=top_k)


def rank_runtime_chunks(
    chunks: list[dict],
    question: str,
    selected_faculty: str,
    idf: dict[str, float] | None = None,
    top_k: int = 4,
) -> dict:
    _sync_retrieval_overrides()
    return _RANK_RUNTIME_CHUNKS_IMPL(chunks, question, selected_faculty, idf=idf, top_k=top_k)
