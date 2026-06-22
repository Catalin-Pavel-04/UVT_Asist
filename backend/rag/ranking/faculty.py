from __future__ import annotations

from rag.constants import GENERAL_FACULTY_ID
from rag.intent_detection import is_central_uvt_contact_query
from rag.query_analysis import QueryAnalysis

def _faculty_score(chunk: dict, analysis: QueryAnalysis, selected_faculty: str) -> tuple[float, list[str]]:
    faculty_id = str(chunk.get("faculty_id") or GENERAL_FACULTY_ID)
    is_policy_document = chunk["_is_institutional_policy"]
    signals: list[str] = []
    score = 0.0

    if selected_faculty == GENERAL_FACULTY_ID:
        if faculty_id == GENERAL_FACULTY_ID:
            score += 34 if analysis.is_policy_question else 18
            signals.append("faculty:uvt")
        elif analysis.is_policy_question and is_policy_document:
            score += 8
            signals.append("faculty:hosted_policy")
        elif analysis.is_policy_question:
            score -= 14
            signals.append("faculty:other_policy_penalty")
        else:
            score -= 28
            signals.append("faculty:other_uvt_scope_penalty")
    else:
        if faculty_id == selected_faculty:
            score += 34
            signals.append("faculty:exact")
        elif faculty_id == GENERAL_FACULTY_ID:
            score += 10 if not analysis.is_policy_question else 22
            signals.append("faculty:uvt")
        elif analysis.is_policy_question and is_policy_document:
            score += 12
            signals.append("faculty:hosted_policy")
        else:
            score -= 48
            signals.append("faculty:mismatch")

    return score, signals
