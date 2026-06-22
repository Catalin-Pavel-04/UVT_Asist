from __future__ import annotations

import re

from rag.constants import (
    CUMULATION_TERMS,
    DOCUMENT_REQUEST_TERMS,
    GENERAL_FACULTY_ID,
    HOUSING_TERMS,
    OFF_TOPIC_SOCIAL_POLICY_TERMS,
    POLICY_DOCUMENT_TERMS,
    SCHOLARSHIP_TERMS,
    SOCIAL_CONTEXT_TERMS,
    STRONG_SOCIAL_CONTEXT_TERMS,
    SUBMISSION_TERMS,
    VOLUNTEERING_CREDIT_TERMS,
    VOLUNTEERING_TERMS,
)
from rag.intent_detection import (
    _is_housing_document_question,
    _is_social_document_question,
    is_volunteering_credit_query,
)
from rag.query_analysis import QueryAnalysis
from rag.ranking.lexical import _contains_any

def _is_institutional_policy_document(
    title_norm: str,
    url_norm: str,
    text_norm: str,
    page_type: str,
    is_document: bool,
) -> bool:
    combined_head = f"{title_norm} {url_norm} {text_norm[:2600]}"
    has_document_terms = _contains_any(combined_head, POLICY_DOCUMENT_TERMS)
    if not has_document_terms:
        return False

    hosted_by_uvt = ".uvt.ro" in url_norm or "uvt.ro" in url_norm
    if is_document and hosted_by_uvt:
        return True

    has_institutional_terms = "universitatea de vest" in combined_head or "www.uvt.ro" in combined_head
    is_policy_page = page_type == "regulamente" and ("uvt.ro/organizare" in url_norm or "www.uvt.ro" in url_norm)
    return has_document_terms and has_institutional_terms and is_policy_page


def _policy_score(chunk: dict, analysis: QueryAnalysis) -> tuple[float, list[str]]:
    if not analysis.is_policy_question:
        return 0.0, []

    page_type = str(chunk.get("page_type") or "general")
    title_norm = chunk["_title_norm"]
    combined = f"{chunk['_title_norm']} {chunk['_url_norm']} {chunk['_text_norm']}"
    topic_head = f"{chunk['_title_norm']} {chunk['_url_norm']} {chunk['_text_norm'][:1800]}"
    query_tokens = set(analysis.expanded_tokens)
    signals: list[str] = []
    score = 0.0

    if chunk["_is_institutional_policy"]:
        score += 52
        signals.append("policy:institutional_document")
    if page_type == "regulamente":
        score += 36
        signals.append("policy:regulations")
    if _contains_any(combined, POLICY_DOCUMENT_TERMS):
        score += 18
        signals.append("policy:document_terms")

    housing_document_question = _is_housing_document_question(query_tokens)
    social_document_question = _is_social_document_question(query_tokens)
    scholarship_question = bool({"burse", "bursa", "burselor"} & query_tokens) or (
        social_document_question and not housing_document_question
    )

    if housing_document_question:
        if _contains_any(topic_head, HOUSING_TERMS):
            score += 34
            signals.append("policy:housing_topic")
        else:
            score -= 18
            signals.append("policy:housing_missing")

        if _contains_any(combined, DOCUMENT_REQUEST_TERMS):
            score += 22
            signals.append("policy:housing_documents")

        if _contains_any(combined, SOCIAL_CONTEXT_TERMS):
            score += 18
            signals.append("policy:social_context")

    if scholarship_question:
        if _contains_any(topic_head, SCHOLARSHIP_TERMS):
            score += 26
            signals.append("policy:scholarship_topic")
            faculty_id = str(chunk.get("faculty_id") or GENERAL_FACULTY_ID)
            if faculty_id == GENERAL_FACULTY_ID and "metodologie" in f"{title_norm} {chunk['_url_norm']}":
                score += 24
                signals.append("policy:uvt_scholarship_methodology")
        else:
            score -= 20
            signals.append("policy:topic_missing")

        if social_document_question:
            title_url_norm = f"{title_norm} {chunk['_url_norm']}"
            if "metodologie" in title_url_norm and "burs" in title_url_norm:
                score += 58
                signals.append("policy:social_scholarship_methodology")
            if _contains_any(combined, ("documentele necesare", "documente justificative")):
                score += 32
                signals.append("policy:social_required_documents")
            if _contains_any(title_url_norm, OFF_TOPIC_SOCIAL_POLICY_TERMS):
                score -= 82
                signals.append("policy:off_topic_social_document")

            has_social_context = _contains_any(combined, STRONG_SOCIAL_CONTEXT_TERMS)
            if has_social_context:
                score += 30
                signals.append("policy:social_support_context")
            else:
                score -= 54
                signals.append("policy:social_context_missing")
            if _contains_any(combined, DOCUMENT_REQUEST_TERMS):
                score += 20
                signals.append("policy:social_documents")
            off_topic_financial_document = _contains_any(
                f"{title_norm} {chunk['_url_norm']}",
                ("doctoranzi", "mobilitati", "cercetare", "doctorat"),
            )
            if off_topic_financial_document and not {"doctorat", "doctoranzi", "mobilitati", "cercetare"} & query_tokens:
                score -= 44
                signals.append("policy:off_topic_financial_document")

    asks_cumulation = bool({"2", "cumulare"} & query_tokens)
    if asks_cumulation:
        if _contains_any(combined, CUMULATION_TERMS):
            score += 44
            signals.append("policy:cumulation")
        elif scholarship_question:
            score -= 18
            signals.append("policy:cumulation_missing")

    volunteering_question = is_volunteering_credit_query(analysis.corrected_question, query_tokens)
    if volunteering_question:
        title_url_norm = f"{title_norm} {chunk['_url_norm']}"
        if _contains_any(title_url_norm, ("oportunitati-de-voluntariat", "oportunitati de voluntariat")):
            score += 36
            signals.append("policy:stable_volunteering_page")
        if "depunerea-portofoliilor" in title_url_norm and re.search(r"/educatie/20\d{2}/\d{2}/", chunk["_path"]):
            score -= 16
            signals.append("policy:dated_volunteering_post")

        has_volunteering_topic = _contains_any(topic_head, VOLUNTEERING_TERMS)
        has_credit_topic = _contains_any(topic_head, VOLUNTEERING_CREDIT_TERMS)
        has_submission_topic = _contains_any(topic_head, SUBMISSION_TERMS)
        has_portfolio_contents = _contains_any(topic_head, ("raport", "adeverinta", "evaluare", "formular"))

        if has_volunteering_topic and has_credit_topic:
            score += 36
            signals.append("policy:volunteering_credit_topic")
        else:
            score -= 18
            signals.append("policy:volunteering_credit_missing")

        if has_submission_topic:
            score += 42
            signals.append("policy:submission_process")
        else:
            score -= 30
            signals.append("policy:submission_missing")

        if has_portfolio_contents:
            score += 28
            signals.append("policy:portfolio_contents")

    if title_norm in {"regulamente - uvt", "legislatie - uvt"} and not _contains_any(combined, SCHOLARSHIP_TERMS + CUMULATION_TERMS):
        score -= 36
        signals.append("policy:generic_regulation_penalty")

    return score, signals
