from __future__ import annotations

import math
from collections import Counter

from ollama_client import embed_text
from rag.confidence import compute_confidence
from rag.constants import GENERAL_FACULTY_ID, HOUSING_TERMS, SEMANTIC_SCORE_WEIGHT, VECTOR_LEXICAL_BACKFILL_ENABLED, VECTOR_SEARCH_LIMIT
from rag.intent_detection import (
    _is_housing_document_question,
    _is_social_document_question,
    is_academic_calendar_query,
    is_central_uvt_contact_query,
    is_volunteering_credit_query,
)
from rag.query_analysis import QueryAnalysis, analyze_query
from rag.ranking.faculty import _faculty_score
from rag.ranking.lexical import _contains_any, _counter, _lexical_score
from rag.ranking.page_type import _is_document_url, _is_homepage, _page_type_score, _specific_page_score, _url_path, _url_slug_tokens
from rag.ranking.policy import _is_institutional_policy_document, _policy_score
from rag.text_normalization import normalize, tokenize
from vector_store import search_chunks

_PREPARED_INDEX_CACHE: dict | None = None
_PREPARED_INDEX_SIGNATURE: tuple | None = None


def _prepare_chunk(chunk: dict) -> dict:
    title = str(chunk.get("title") or "")
    url = str(chunk.get("url") or "")
    chunk_text = str(chunk.get("chunk_text") or chunk.get("chunk") or "")
    page_type = str(chunk.get("page_type") or "general")
    is_document = _is_document_url(url)

    title_norm = normalize(title)
    url_norm = normalize(url)
    text_norm = normalize(chunk_text)
    title_tokens = tokenize(title)
    url_tokens = _url_slug_tokens(url)
    text_tokens = tokenize(chunk_text)
    token_set = set(title_tokens + url_tokens + text_tokens)

    return {
        **chunk,
        "_title_norm": title_norm,
        "_url_norm": url_norm,
        "_text_norm": text_norm,
        "_title_tokens": title_tokens,
        "_url_tokens": url_tokens,
        "_text_tokens": text_tokens,
        "_title_counter": _counter(title_tokens),
        "_url_counter": _counter(url_tokens),
        "_text_counter": _counter(text_tokens),
        "_token_set": token_set,
        "_path": _url_path(url),
        "_is_homepage": _is_homepage(url),
        "_is_document": is_document,
        "_is_institutional_policy": _is_institutional_policy_document(
            title_norm,
            url_norm,
            text_norm,
            page_type,
            is_document,
        ),
    }


def prepare_index(index_document: dict) -> dict:
    global _PREPARED_INDEX_CACHE, _PREPARED_INDEX_SIGNATURE

    signature = (
        index_document.get("schema_version"),
        index_document.get("built_at"),
        index_document.get("chunk_count"),
    )
    if _PREPARED_INDEX_CACHE is not None and _PREPARED_INDEX_SIGNATURE == signature:
        return _PREPARED_INDEX_CACHE

    chunks = [
        _prepare_chunk(chunk)
        for chunk in index_document.get("chunks", [])
        if isinstance(chunk, dict) and chunk.get("chunk_text")
    ]
    document_frequency = Counter()
    for chunk in chunks:
        document_frequency.update(chunk["_token_set"])

    total_chunks = max(1, len(chunks))
    idf = {
        token: math.log(1 + (total_chunks - frequency + 0.5) / (frequency + 0.5))
        for token, frequency in document_frequency.items()
    }

    prepared = {"signature": signature, "chunks": chunks, "idf": idf}
    _PREPARED_INDEX_CACHE = prepared
    _PREPARED_INDEX_SIGNATURE = signature
    return prepared


def score_chunk_candidate(
    prepared_chunk: dict,
    analysis: QueryAnalysis,
    selected_faculty: str,
    idf: dict[str, float],
) -> dict:
    score = 0.0
    signals: list[str] = []

    for component_score, component_signals in (
        _lexical_score(prepared_chunk, analysis, idf),
        _faculty_score(prepared_chunk, analysis, selected_faculty),
        _page_type_score(prepared_chunk, analysis),
        _specific_page_score(prepared_chunk, analysis),
        _policy_score(prepared_chunk, analysis),
    ):
        score += component_score
        signals.extend(component_signals)

    return {
        "chunk_id": prepared_chunk.get("chunk_id"),
        "faculty_id": prepared_chunk.get("faculty_id", GENERAL_FACULTY_ID),
        "page_type": prepared_chunk.get("page_type", "general"),
        "title": prepared_chunk.get("title", prepared_chunk.get("url", "")),
        "url": prepared_chunk.get("url", ""),
        "chunk_text": prepared_chunk.get("chunk_text", ""),
        "last_indexed": prepared_chunk.get("last_indexed"),
        "retrieval_score": round(max(0.0, score), 3),
        "match_signals": list(dict.fromkeys(signals)),
    }


def _candidate_allowed(chunk: dict, analysis: QueryAnalysis, selected_faculty: str) -> bool:
    faculty_id = str(chunk.get("faculty_id") or GENERAL_FACULTY_ID)
    if selected_faculty == GENERAL_FACULTY_ID:
        return True
    if faculty_id in {selected_faculty, GENERAL_FACULTY_ID}:
        return True
    return analysis.is_policy_question and chunk.get("_is_institutional_policy", False)


def _prefer_policy_candidates(scored: list[dict], analysis: QueryAnalysis) -> list[dict]:
    if not analysis.is_policy_question:
        return scored

    query_tokens = set(analysis.expanded_tokens)

    if is_volunteering_credit_query(analysis.corrected_question, analysis.expanded_tokens):
        volunteering_candidates = [
            chunk for chunk in scored
            if "policy:volunteering_credit_topic" in chunk.get("match_signals", [])
        ]
        submission_candidates = [
            chunk for chunk in volunteering_candidates
            if "policy:submission_process" in chunk.get("match_signals", [])
        ]
        if submission_candidates:
            return submission_candidates
        if volunteering_candidates:
            scored = volunteering_candidates

    if _is_housing_document_question(query_tokens):
        housing_candidates = [
            chunk for chunk in scored
            if "policy:housing_topic" in chunk.get("match_signals", [])
            or _contains_any(normalize(f"{chunk.get('title', '')} {chunk.get('url', '')}"), HOUSING_TERMS)
        ]
        if housing_candidates:
            scored = housing_candidates

    if _is_social_document_question(query_tokens) and not _is_housing_document_question(query_tokens):
        social_candidates = [
            chunk for chunk in scored
            if "burs" in normalize(
                f"{chunk.get('title', '')} {chunk.get('url', '')} {str(chunk.get('chunk_text', ''))[:1800]}"
            )
        ]
        if social_candidates:
            scored = social_candidates

    if {"burse", "bursa", "burselor"} & query_tokens:
        topic_candidates = [
            chunk for chunk in scored
            if "policy:scholarship_topic" in chunk.get("match_signals", [])
        ]
        if topic_candidates:
            strict_topic_candidates = [
                chunk for chunk in topic_candidates
                if chunk.get("page_type") in {"regulamente", "burse"}
                or "burs" in normalize(f"{chunk.get('title', '')} {chunk.get('url', '')}")
            ]
            scored = strict_topic_candidates or topic_candidates

    preferred = [
        chunk for chunk in scored
        if chunk.get("page_type") == "regulamente"
        or any(signal.startswith("policy:institutional") for signal in chunk.get("match_signals", []))
    ]
    return preferred if preferred else scored


def _prefer_academic_calendar_candidates(scored: list[dict], analysis: QueryAnalysis) -> list[dict]:
    if not is_academic_calendar_query(analysis.corrected_question, analysis.tokens):
        return scored

    calendar_candidates = [
        chunk for chunk in scored
        if "academic_calendar" in chunk.get("match_signals", [])
        or _contains_any(
            normalize(f"{chunk.get('title', '')} {chunk.get('url', '')} {chunk.get('chunk_text', '')[:1800]}"),
            ("structura anului universitar", "structura-anului-universitar", "calendar academic"),
        )
    ]
    return calendar_candidates if calendar_candidates else scored


def _prefer_selected_scope_candidates(scored: list[dict], selected_faculty: str) -> list[dict]:
    if selected_faculty != GENERAL_FACULTY_ID or not scored:
        return scored

    central_candidates = [
        chunk for chunk in scored
        if str(chunk.get("faculty_id") or GENERAL_FACULTY_ID) == GENERAL_FACULTY_ID
    ]
    if not central_candidates:
        return scored

    best_score = max(float(chunk.get("retrieval_score", 0) or 0) for chunk in scored)
    best_central_score = max(float(chunk.get("retrieval_score", 0) or 0) for chunk in central_candidates)
    if best_central_score >= best_score * 0.72:
        return central_candidates
    return scored


def select_diverse_chunks(scored_chunks: list[dict], top_k: int, max_chunks_per_url: int = 1) -> list[dict]:
    selected: list[dict] = []
    url_counts: dict[str, int] = {}

    for chunk in scored_chunks:
        url = chunk.get("url", "")
        if not url:
            continue
        if url_counts.get(url, 0) >= max_chunks_per_url:
            continue

        selected.append(chunk)
        url_counts[url] = url_counts.get(url, 0) + 1
        if len(selected) >= top_k:
            break

    return selected


def max_chunks_per_url_for_analysis(analysis: QueryAnalysis) -> int:
    query_tokens = set(analysis.expanded_tokens)
    if _is_housing_document_question(query_tokens) or _is_social_document_question(query_tokens):
        return 4
    if analysis.is_policy_question:
        return 2
    return 1


def build_query_embedding_text(question: str, analysis: QueryAnalysis) -> str:
    return (
        f"Intrebare student: {question}\n"
        f"Intrebare normalizata: {analysis.corrected_question}\n"
        f"Intent: {analysis.intent}\n"
        f"Intrebare de regulament/metodologie: {analysis.is_policy_question}\n"
        f"Termeni importanti: {' '.join(analysis.expanded_tokens)}"
    )


def build_query_embedding_texts(question: str, analysis: QueryAnalysis) -> list[str]:
    texts = [build_query_embedding_text(question, analysis)]
    query_tokens = set(analysis.expanded_tokens)

    if analysis.intent == "contact":
        texts.append(
            "Intrebare student despre pagina oficiala de contact UVT.\n"
            "Cautare prioritara: Contact Universitatea de Vest din Timisoara, adresa, telefon, email, InfoCentru, rectorat."
        )

    if is_academic_calendar_query(analysis.corrected_question, analysis.tokens):
        texts.append(
            "Intrebare student despre calendarul academic UVT.\n"
            "Cautare prioritara: Structura anului universitar. "
            "Saptamani de cursuri, semestrul I, semestrul al doilea, sesiuni de examene, vacante, anul universitar."
        )

    if _is_social_document_question(query_tokens) and not _is_housing_document_question(query_tokens):
        texts.append(
            "Intrebare student despre acte pentru bursa sociala.\n"
            "Cautare prioritara: Metodologie privind acordarea burselor. "
            "Anexa documentele necesare pentru bursele sociale. "
            "Studenti din familii monoparentale, parinti divortati, orfani, venituri, documente justificative."
        )

    if _is_housing_document_question(query_tokens):
        texts.append(
            "Intrebare student despre dosarul de cazare in caminele UVT.\n"
            "Cautare prioritara: Regulament de cazare in caminele UVT. "
            "Cazuri sociale, orfan de parinte, familie monoparentala, documente justificative, criterii sociale."
        )

    return texts


def vector_search_limit_for_analysis(analysis: QueryAnalysis) -> int:
    query_tokens = set(analysis.expanded_tokens)
    if analysis.intent in {"orar", "contact"}:
        return max(VECTOR_SEARCH_LIMIT, 60)
    if is_academic_calendar_query(analysis.corrected_question, analysis.tokens):
        return max(VECTOR_SEARCH_LIMIT, 80)
    if _is_social_document_question(query_tokens):
        return max(VECTOR_SEARCH_LIMIT, 60)
    if _is_housing_document_question(query_tokens):
        return max(VECTOR_SEARCH_LIMIT, 36)
    if analysis.is_policy_question:
        return max(VECTOR_SEARCH_LIMIT, 24)
    return VECTOR_SEARCH_LIMIT


def _vector_search_passes(analysis: QueryAnalysis, selected_faculty: str) -> list[dict]:
    preferred_page_types = list(analysis.page_type_preferences[:4])
    passes: list[dict] = []

    def add_pass(faculty_ids: list[str] | None, page_types: list[str] | None, label: str) -> None:
        candidate = {
            "faculty_ids": faculty_ids,
            "page_types": page_types,
            "label": label,
        }
        if candidate not in passes:
            passes.append(candidate)

    if selected_faculty != GENERAL_FACULTY_ID:
        add_pass([selected_faculty], preferred_page_types, "selected_faculty_page_type")
        add_pass([selected_faculty], None, "selected_faculty")
        if analysis.is_policy_question:
            add_pass([GENERAL_FACULTY_ID], preferred_page_types, "uvt_policy_page_type")
            add_pass([GENERAL_FACULTY_ID], None, "uvt_policy")
        else:
            add_pass([selected_faculty, GENERAL_FACULTY_ID], preferred_page_types, "faculty_or_uvt_page_type")
    else:
        add_pass([GENERAL_FACULTY_ID], preferred_page_types, "uvt_page_type")
        add_pass([GENERAL_FACULTY_ID], None, "uvt")

    add_pass(None, preferred_page_types, "any_faculty_page_type")
    add_pass(None, None, "any_faculty")
    return passes


def _merge_semantic_hits(hit_groups: list[tuple[str, list[dict]]]) -> list[dict]:
    merged: dict[str, dict] = {}
    for label, hits in hit_groups:
        for hit in hits:
            chunk_id = str(hit.get("chunk_id") or "")
            if not chunk_id:
                continue
            previous = merged.get(chunk_id)
            if previous is None or float(hit.get("semantic_score", 0)) > float(previous.get("semantic_score", 0)):
                merged[chunk_id] = {**hit, "vector_filter": label}
            else:
                previous.setdefault("vector_filter", label)
    return list(merged.values())


def _retrieve_semantic_candidates(question: str, analysis: QueryAnalysis, selected_faculty: str) -> list[dict]:
    hit_groups: list[tuple[str, list[dict]]] = []
    search_limit = vector_search_limit_for_analysis(analysis)

    for query_index, query_text in enumerate(build_query_embedding_texts(question, analysis), start=1):
        query_vector = embed_text(query_text)
        for search_pass in _vector_search_passes(analysis, selected_faculty):
            hits = search_chunks(
                query_vector=query_vector,
                faculty_ids=search_pass["faculty_ids"],
                page_types=search_pass["page_types"],
                limit=search_limit,
            )
            label = search_pass["label"] if query_index == 1 else f"{search_pass['label']}:targeted"
            hit_groups.append((label, hits))

    return _merge_semantic_hits(hit_groups)


def _score_semantic_candidates(
    hits: list[dict],
    analysis: QueryAnalysis,
    selected_faculty: str,
    idf: dict[str, float],
) -> list[dict]:
    scored: list[dict] = []

    for hit in hits:
        prepared_chunk = _prepare_chunk(hit)
        if not _candidate_allowed(prepared_chunk, analysis, selected_faculty):
            continue

        candidate = score_chunk_candidate(prepared_chunk, analysis, selected_faculty, idf)
        semantic_score = float(hit.get("semantic_score", 0.0) or 0.0)
        if semantic_score <= 0 and candidate["retrieval_score"] <= 0:
            continue

        candidate["semantic_score"] = round(semantic_score, 6)
        candidate["vector_filter"] = hit.get("vector_filter", "")
        candidate["retrieval_score"] = round(
            candidate["retrieval_score"] + semantic_score * SEMANTIC_SCORE_WEIGHT,
            3,
        )
        candidate["match_signals"] = list(dict.fromkeys([
            *candidate.get("match_signals", []),
            f"semantic:{semantic_score:.2f}",
            f"vector_filter:{hit.get('vector_filter', 'unknown')}",
        ]))
        scored.append(candidate)

    scored = _prefer_policy_candidates(scored, analysis)
    scored = _prefer_academic_calendar_candidates(scored, analysis)
    scored = _prefer_selected_scope_candidates(scored, selected_faculty)
    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    return scored


def _score_lexical_backfill_candidates(
    prepared_chunks: list[dict],
    analysis: QueryAnalysis,
    selected_faculty: str,
    idf: dict[str, float],
    limit: int = 30,
) -> list[dict]:
    scored: list[dict] = []
    for prepared_chunk in prepared_chunks:
        if not _candidate_allowed(prepared_chunk, analysis, selected_faculty):
            continue
        candidate = score_chunk_candidate(prepared_chunk, analysis, selected_faculty, idf)
        if candidate["retrieval_score"] <= 0:
            continue
        candidate["semantic_score"] = 0.0
        candidate["vector_filter"] = "lexical_backfill"
        candidate["match_signals"] = list(dict.fromkeys([
            *candidate.get("match_signals", []),
            "lexical_backfill",
        ]))
        scored.append(candidate)

    scored = _prefer_policy_candidates(scored, analysis)
    scored = _prefer_academic_calendar_candidates(scored, analysis)
    scored = _prefer_selected_scope_candidates(scored, selected_faculty)
    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    return scored[:limit]


def _merge_scored_candidates(candidate_groups: list[list[dict]]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in candidate_groups:
        for candidate in group:
            chunk_id = str(candidate.get("chunk_id") or "")
            if not chunk_id:
                continue
            previous = merged.get(chunk_id)
            if previous is None or candidate.get("retrieval_score", 0) > previous.get("retrieval_score", 0):
                merged[chunk_id] = dict(candidate)
            else:
                previous["match_signals"] = list(dict.fromkeys([
                    *previous.get("match_signals", []),
                    *candidate.get("match_signals", []),
                ]))

    scored = list(merged.values())
    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    return scored


def _canonical_central_contact_candidates(index_document: dict, analysis: QueryAnalysis) -> list[dict]:
    if not is_central_uvt_contact_query(analysis):
        return []

    candidates: list[dict] = []
    for chunk in index_document.get("chunks", []):
        if str(chunk.get("faculty_id") or GENERAL_FACULTY_ID) != GENERAL_FACULTY_ID:
            continue
        if str(chunk.get("url") or "").rstrip("/") != "https://uvt.ro/contact":
            continue
        prepared_chunk = _prepare_chunk(chunk)
        candidate = score_chunk_candidate(prepared_chunk, analysis, GENERAL_FACULTY_ID, {})
        candidate["retrieval_score"] = max(float(candidate.get("retrieval_score", 0) or 0), 180.0)
        candidate["semantic_score"] = 0.0
        candidate["vector_filter"] = "canonical_contact"
        candidate["match_signals"] = list(dict.fromkeys([
            *candidate.get("match_signals", []),
            "canonical_contact",
        ]))
        candidates.append(candidate)
        if len(candidates) >= 2:
            break

    return candidates


def rank_vector_index(question: str, index_document: dict, selected_faculty: str, top_k: int = 6) -> dict:
    analysis = analyze_query(question)
    semantic_hits = _retrieve_semantic_candidates(question, analysis, selected_faculty)
    scored = _score_semantic_candidates(
        semantic_hits,
        analysis,
        selected_faculty,
        {},
    )
    if VECTOR_LEXICAL_BACKFILL_ENABLED and not scored:
        prepared_index = prepare_index(index_document)
        lexical_backfill = _score_lexical_backfill_candidates(
            prepared_index.get("chunks", []),
            analysis,
            selected_faculty,
            prepared_index.get("idf", {}),
        )
        scored = _merge_scored_candidates([scored, lexical_backfill])
    if selected_faculty == GENERAL_FACULTY_ID:
        scored = _merge_scored_candidates([scored, _canonical_central_contact_candidates(index_document, analysis)])

    chunks = select_diverse_chunks(
        scored,
        top_k=top_k,
        max_chunks_per_url=max_chunks_per_url_for_analysis(analysis),
    )
    confidence = compute_confidence(chunks, analysis)

    return {
        "analysis": analysis.to_dict(),
        "chunks": chunks,
        "confidence": confidence["label"],
        "confidence_score": confidence["score"],
        "confidence_reason": confidence["reason"],
        "retrieval_backend": "qdrant",
        "candidate_count": len(semantic_hits),
    }


def rank_lexical_index(question: str, index_document: dict, selected_faculty: str, top_k: int = 6) -> dict:
    analysis = analyze_query(question)
    prepared_index = prepare_index(index_document)
    scored: list[dict] = []

    for prepared_chunk in prepared_index["chunks"]:
        if not _candidate_allowed(prepared_chunk, analysis, selected_faculty):
            continue
        candidate = score_chunk_candidate(prepared_chunk, analysis, selected_faculty, prepared_index["idf"])
        if candidate["retrieval_score"] > 0:
            scored.append(candidate)

    scored = _prefer_policy_candidates(scored, analysis)
    scored = _prefer_academic_calendar_candidates(scored, analysis)
    scored = _prefer_selected_scope_candidates(scored, selected_faculty)
    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    chunks = select_diverse_chunks(
        scored,
        top_k=top_k,
        max_chunks_per_url=max_chunks_per_url_for_analysis(analysis),
    )
    confidence = compute_confidence(chunks, analysis)

    return {
        "analysis": analysis.to_dict(),
        "chunks": chunks,
        "confidence": confidence["label"],
        "confidence_score": confidence["score"],
        "confidence_reason": confidence["reason"],
        "retrieval_backend": "local_json_lexical",
    }


def rank_index(question: str, index_document: dict, selected_faculty: str, top_k: int = 6) -> dict:
    try:
        result = rank_vector_index(question, index_document, selected_faculty, top_k=top_k)
        if result.get("chunks"):
            return result
        result["confidence_reason"] = "Qdrant a raspuns, dar nu a returnat fragmente oficiale relevante."
        return result
    except Exception as exc:
        result = rank_lexical_index(question, index_document, selected_faculty, top_k=top_k)
        result["retrieval_backend"] = "local_json_fallback"
        result["vector_error"] = str(exc)
        result["confidence_reason"] = (
            f"{result.get('confidence_reason', '')} "
            "Fallback lexical folosit deoarece Qdrant sau Ollama nu este disponibil."
        ).strip()
        return result


def rank_runtime_chunks(
    chunks: list[dict],
    question: str,
    selected_faculty: str,
    idf: dict[str, float] | None = None,
    top_k: int = 4,
) -> dict:
    analysis = analyze_query(question)
    prepared_chunks = [_prepare_chunk(chunk) for chunk in chunks if chunk.get("chunk_text")]
    scored = [
        score_chunk_candidate(chunk, analysis, selected_faculty, idf or {})
        for chunk in prepared_chunks
        if _candidate_allowed(chunk, analysis, selected_faculty)
    ]
    scored = [chunk for chunk in scored if chunk["retrieval_score"] > 0]
    scored = _prefer_policy_candidates(scored, analysis)
    scored = _prefer_academic_calendar_candidates(scored, analysis)
    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    selected = select_diverse_chunks(scored, top_k=top_k, max_chunks_per_url=max_chunks_per_url_for_analysis(analysis))
    confidence = compute_confidence(selected, analysis)

    return {
        "analysis": analysis.to_dict(),
        "chunks": selected,
        "confidence": confidence["label"],
        "confidence_score": confidence["score"],
        "confidence_reason": confidence["reason"],
    }
