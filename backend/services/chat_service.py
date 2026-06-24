from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from core.config import CHAT_CACHE_VERSION, LIVE_VERIFY_ENABLED, LIVE_VERIFY_LIMIT
from faculties import FACULTIES
from ollama_client import ask_ollama_json
from page_index import build_chunk_entries_from_pages, get_index_status, load_index, metadata_index_document, normalize_url
from prompts import build_user_prompt
from rag.confidence import compute_confidence
from rag.query_analysis import analyze_query
from rag.retrieval_service import rank_index, rank_lexical_index, rank_runtime_chunks
from rag.text_normalization import normalize as normalize_retrieval_text
from services.answer_generation_service import (
    answer_needs_fallback as _answer_needs_fallback,
    ask_ollama_answer as _ask_ollama_answer,
    generate_answer_with_fallback,
    repair_generated_answer as _repair_generated_answer,
)
from services.chat_cache import (
    RESPONSE_CACHE,
    build_cache_key as _build_cache_key,
    get_cached_response,
    get_response_cache_size,
    set_cached_response,
)
from services.chat_guards import (
    empty_question_payload,
    indexing_in_progress_payload,
    is_unsupported_question,
    is_vague_question,
    needs_faculty_clarification,
    query_analysis_clarification_payload,
    unsupported_question_payload,
    vague_question_payload,
)
from services.chat_models import FACULTY_MAP, GENERAL_FACULTY_ID, ChatRequest, get_faculty
from services.chat_request_parser import compact_text, normalize_match_text, normalize_payload, parse_chat_request
from services.indexing_service import indexing_blocks_chat
from services.response_builder import (
    append_confidence_reason,
    build_local_fallback_answer,
    build_response_payload,
    faculty_clarification_payload,
    unique_sources_from_chunks,
)
from services.source_navigation_service import (
    build_source_navigation_answer,
    ensure_canonical_uvt_contact_source as _ensure_canonical_uvt_contact_source,
    should_use_source_navigation_answer,
    source_navigation_topic,
)
from site_cache import verify_pages
from vector_store import get_vector_index_status

LIVE_VERIFY_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _analysis_faculty_hint(analysis) -> str:
    if analysis is None:
        return ""
    if isinstance(analysis, dict):
        return normalize_match_text(analysis.get("faculty_hint", ""))
    return normalize_match_text(getattr(analysis, "faculty_hint", ""))


def infer_faculty(requested_faculty_id: str, question: str, history: list[dict], analysis=None) -> dict:
    selected_faculty = get_faculty(requested_faculty_id)
    if selected_faculty["id"] != GENERAL_FACULTY_ID:
        return selected_faculty

    faculty_hint = _analysis_faculty_hint(analysis)
    if faculty_hint in FACULTY_MAP and faculty_hint != GENERAL_FACULTY_ID:
        return FACULTY_MAP[faculty_hint]

    return selected_faculty


def build_effective_question(question: str, history: list[dict]) -> str:
    if not is_vague_question(question):
        return question

    context = [item["content"] for item in history[-3:] if item.get("content")]
    context.append(question)
    return " ".join(context)


def build_cache_key(
    faculty_id: str,
    effective_question: str,
    history: list[dict],
    index_built_at: str | None,
    vector_points_count: int | None,
) -> str:
    return _build_cache_key(
        faculty_id,
        effective_question,
        history,
        index_built_at,
        vector_points_count,
        chat_cache_version=CHAT_CACHE_VERSION,
    )


def ask_ollama_answer(answer_prompt: str) -> str:
    return _ask_ollama_answer(answer_prompt, ask_ollama_json_func=ask_ollama_json)


def repair_generated_answer(prompt: str, flawed_answer: str) -> str | None:
    return _repair_generated_answer(prompt, flawed_answer, ask_ollama_json_func=ask_ollama_json)


def answer_needs_fallback(answer: str) -> bool:
    return _answer_needs_fallback(answer)


def merge_ranked_chunks(primary_chunks: list[dict], verified_chunks: list[dict]) -> list[dict]:
    verified_by_url: dict[str, list[dict]] = {}
    for chunk in verified_chunks:
        normalized_url = normalize_url(chunk.get("url", ""))
        if not normalized_url:
            continue
        verified_by_url.setdefault(normalized_url, []).append(dict(chunk))

    for chunks in verified_by_url.values():
        chunks.sort(key=lambda item: item.get("retrieval_score", 0), reverse=True)

    merged: list[dict] = []
    used_verified_chunk_ids: set[str] = set()
    verified_offsets: dict[str, int] = {}
    primary_urls: set[str] = set()
    for primary_chunk in primary_chunks:
        normalized_url = normalize_url(primary_chunk.get("url", ""))
        if not normalized_url:
            continue

        merged_chunk = dict(primary_chunk)
        primary_urls.add(normalized_url)
        verified_candidates = verified_by_url.get(normalized_url, [])
        offset = verified_offsets.get(normalized_url, 0)
        verified_chunk = verified_candidates[offset] if offset < len(verified_candidates) else None
        if verified_chunk:
            merged_chunk["title"] = verified_chunk.get("title") or merged_chunk.get("title")
            merged_chunk["chunk_text"] = verified_chunk.get("chunk_text") or merged_chunk.get("chunk_text")
            merged_chunk["verified"] = True
            verified_offsets[normalized_url] = offset + 1
            if verified_chunk.get("chunk_id"):
                used_verified_chunk_ids.add(str(verified_chunk["chunk_id"]))
        merged.append(merged_chunk)

    remaining_verified_chunks = [
        chunk
        for chunks in verified_by_url.values()
        for chunk in chunks
        if str(chunk.get("chunk_id") or "") not in used_verified_chunk_ids
    ]
    for verified_chunk in sorted(remaining_verified_chunks, key=lambda item: item.get("retrieval_score", 0), reverse=True):
        normalized_url = normalize_url(verified_chunk.get("url", ""))
        if normalized_url and normalized_url not in primary_urls:
            merged.append(verified_chunk)
            primary_urls.add(normalized_url)

    return merged


def live_verify_retrieval(
    effective_question: str,
    faculty_id: str,
    retrieval_result: dict,
    index_document: dict,
) -> tuple[list[dict], bool]:
    if not LIVE_VERIFY_ENABLED or LIVE_VERIFY_LIMIT <= 0:
        return retrieval_result.get("chunks", []), False

    top_urls = [chunk.get("url") for chunk in retrieval_result.get("chunks", []) if chunk.get("url")]
    deep_document_verify = should_deep_verify_documents(retrieval_result)
    verified_pages = verify_pages(top_urls, max_pages=LIVE_VERIFY_LIMIT, index_mode=deep_document_verify)
    if not verified_pages:
        return retrieval_result.get("chunks", []), False

    verified_chunks = build_chunk_entries_from_pages(verified_pages, FACULTIES)
    verified_result = rank_runtime_chunks(
        verified_chunks,
        effective_question,
        faculty_id,
        idf={},
        top_k=4,
    )
    verified_urls = {normalize_url(page.get("url", "")) for page in verified_pages if page.get("url")}
    merged_chunks = merge_ranked_chunks(retrieval_result.get("chunks", []), verified_result.get("chunks", []))

    for chunk in merged_chunks:
        if normalize_url(chunk.get("url", "")) in verified_urls:
            chunk["verified"] = True

    return merged_chunks[:6], True


def is_document_source_url(url: str) -> bool:
    return Path(urlparse(str(url)).path.lower()).suffix in LIVE_VERIFY_DOCUMENT_EXTENSIONS


def should_deep_verify_documents(retrieval_result: dict) -> bool:
    analysis = retrieval_result.get("analysis", {})
    if not analysis.get("is_policy_question"):
        return False
    return any(is_document_source_url(chunk.get("url", "")) for chunk in retrieval_result.get("chunks", []))


def refresh_confidence(retrieval_result: dict, chunks: list[dict]) -> None:
    confidence = compute_confidence(chunks[:4], retrieval_result.get("analysis"))
    retrieval_result["chunks"] = chunks[:4]
    retrieval_result["confidence"] = confidence["label"]
    retrieval_result["confidence_score"] = confidence["score"]
    retrieval_result["confidence_reason"] = confidence["reason"]


def ensure_canonical_uvt_contact_source(question: str, faculty: dict, retrieval_result: dict) -> dict:
    return _ensure_canonical_uvt_contact_source(
        question,
        faculty,
        retrieval_result,
        load_index_func=load_index,
    )


def should_skip_generation(retrieval_result: dict) -> bool:
    return not retrieval_result.get("chunks")


def vector_runtime_ready(vector_status: dict) -> bool:
    return bool(vector_status.get("available") and vector_status.get("points_count"))


def load_runtime_index_document(vector_status: dict) -> dict:
    if vector_runtime_ready(vector_status):
        return metadata_index_document(get_index_status())
    return load_index()


def is_metadata_only_index_document(index_document: dict) -> bool:
    try:
        chunk_count = int(index_document.get("chunk_count") or 0)
    except (TypeError, ValueError):
        chunk_count = 0
    return chunk_count > 0 and not index_document.get("chunks")


def should_retry_full_json_fallback(retrieval_result: dict, index_document: dict) -> bool:
    return not retrieval_result.get("chunks") and is_metadata_only_index_document(index_document)


def rank_with_full_json_fallback(
    question: str,
    index_document: dict,
    selected_faculty: str,
    top_k: int = 6,
) -> dict:
    retrieval_result = rank_index(question, index_document, selected_faculty, top_k=top_k)
    if not should_retry_full_json_fallback(retrieval_result, index_document):
        return retrieval_result

    vector_error = retrieval_result.get("vector_error")
    try:
        full_index_document = load_index()
        if not full_index_document.get("chunks"):
            return retrieval_result
        fallback_result = rank_lexical_index(question, full_index_document, selected_faculty, top_k=top_k)
    except Exception as exc:
        retrieval_result["fallback_error"] = compact_text(exc, 800)
        retrieval_result["confidence_reason"] = append_confidence_reason(
            retrieval_result.get("confidence_reason"),
            "Fallback-ul lexical complet nu a putut incarca indexul JSON.",
        )
        return retrieval_result

    fallback_result["retrieval_backend"] = "local_json_fallback"
    if vector_error:
        fallback_result["vector_error"] = vector_error
    fallback_result["confidence_reason"] = append_confidence_reason(
        fallback_result.get("confidence_reason"),
        "Fallback lexical folosit dupa ce cautarea vectoriala nu a returnat fragmente utilizabile.",
    )
    return fallback_result


def handle_chat(payload) -> tuple[dict, int]:
    chat_request = parse_chat_request(payload)
    if not chat_request.question:
        return empty_question_payload(), 200
    if is_unsupported_question(chat_request.question):
        return unsupported_question_payload(chat_request), 200
    if indexing_blocks_chat():
        return indexing_in_progress_payload(chat_request), 503

    query_analysis = analyze_query(chat_request.question)
    if query_analysis.requires_clarification:
        return query_analysis_clarification_payload(chat_request, query_analysis), 200
    if is_vague_question(chat_request.question) and not chat_request.history:
        return vague_question_payload(chat_request), 200

    faculty = infer_faculty(
        chat_request.requested_faculty_id,
        chat_request.question,
        chat_request.history,
        analysis=query_analysis,
    )
    effective_question = build_effective_question(chat_request.question, chat_request.history)
    question_is_vague = is_vague_question(chat_request.question)
    vector_status = get_vector_index_status()
    index_document = load_runtime_index_document(vector_status)

    cache_key = build_cache_key(
        faculty["id"],
        effective_question,
        chat_request.history,
        index_document.get("built_at"),
        vector_status.get("points_count"),
    )
    cached_response = get_cached_response(cache_key)
    if cached_response is not None:
        return cached_response, 200

    retrieval_result = rank_with_full_json_fallback(effective_question, index_document, faculty["id"], top_k=6)
    if needs_faculty_clarification(faculty, retrieval_result):
        response_payload = faculty_clarification_payload(faculty, retrieval_result)
        set_cached_response(cache_key, response_payload)
        return response_payload, 200

    retrieval_result = ensure_canonical_uvt_contact_source(chat_request.question, faculty, retrieval_result)

    live_verified = False

    if retrieval_result.get("chunks"):
        merged_chunks, live_verified = live_verify_retrieval(
            effective_question,
            faculty["id"],
            retrieval_result,
            index_document,
        )
        refresh_confidence(retrieval_result, merged_chunks)

    if should_use_source_navigation_answer(chat_request.question, retrieval_result):
        generation = {"mode": "local_source_navigation"}
        answer = build_source_navigation_answer(chat_request.question, retrieval_result)
    elif should_skip_generation(retrieval_result):
        generation = {"mode": "fallback_low_evidence"}
        answer = build_local_fallback_answer(
            retrieval_result,
            reason="Nu exista context oficial selectat pentru generarea cu Ollama.",
        )
    else:
        prompt = build_user_prompt(
            chat_request.question,
            faculty["name"],
            retrieval_result,
            history=chat_request.history,
            question_is_vague=question_is_vague,
        )
        answer, generation = generate_answer_with_fallback(
            prompt,
            retrieval_result,
            ask_ollama_json_func=ask_ollama_json,
        )

    response_payload = build_response_payload(answer, faculty, retrieval_result, live_verified, generation)
    set_cached_response(cache_key, response_payload)
    return response_payload, 200
