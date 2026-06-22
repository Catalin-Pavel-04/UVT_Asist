from __future__ import annotations

from typing import Iterable

from rag.constants import (
    CUMULATION_TERMS,
    DOCUMENT_REQUEST_TERMS,
    HOUSING_TERMS,
    INTENT_KEYWORDS,
    POLICY_PHRASES,
    SCHOLARSHIP_TERMS,
    SOCIAL_CONTEXT_TERMS,
    SUBMISSION_TERMS,
    VOLUNTEERING_CREDIT_TERMS,
    VOLUNTEERING_TERMS,
)
from rag.text_normalization import normalize, tokenize

def _has_document_request(tokens: Iterable[str]) -> bool:
    return bool(set(tokens) & set(DOCUMENT_REQUEST_TERMS))


def _has_social_context(tokens: Iterable[str]) -> bool:
    return bool(set(tokens) & set(SOCIAL_CONTEXT_TERMS))


def _has_housing_context(tokens: Iterable[str]) -> bool:
    return bool(set(tokens) & set(HOUSING_TERMS))


def _is_social_document_question(tokens: Iterable[str]) -> bool:
    token_set = set(tokens)
    return _has_document_request(token_set) and _has_social_context(token_set)


def _is_housing_document_question(tokens: Iterable[str]) -> bool:
    token_set = set(tokens)
    return _has_document_request(token_set) and _has_housing_context(token_set)


def is_academic_calendar_query(question_text: str, tokens: Iterable[str]) -> bool:
    token_set = set(tokens)
    normalized_question = normalize(question_text)
    if {"semestru", "sesiune", "sesiuni", "vacante", "saptamani"} & token_set:
        return True
    if "calendar academic" in normalized_question or "structura anului" in normalized_question:
        return True
    return bool({"calendar", "structura"} & token_set and {"an", "universitar"} & token_set)


def is_central_uvt_contact_query(analysis: "QueryAnalysis") -> bool:
    if analysis.intent != "contact":
        return False
    normalized_question = normalize(analysis.corrected_question)
    return (
        "uvt" in normalized_question
        or "universitate" in normalized_question
        or "administrativ" in normalized_question
    )


def _score_intents(question: str, tokens: Iterable[str]) -> dict[str, int]:
    token_set = set(tokens)
    question_text = normalize(question)
    scores = {intent: 0 for intent in INTENT_KEYWORDS}

    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            keyword_norm = normalize(keyword)
            if " " in keyword_norm and keyword_norm in question_text:
                scores[intent] += 4
            elif keyword_norm in token_set:
                scores[intent] += 3
            elif keyword_norm in question_text:
                scores[intent] += 1

    if "program" in token_set and {"secretariat", "contact"} & token_set:
        scores["contact"] += 4
    if {"orar", "orare"} & token_set:
        scores["orar"] += 5
    if "dosar" in token_set and ({"admitere", "inscriere", "candidat"} & token_set or "dosar de admitere" in question_text):
        scores["admitere"] += 4
    if {"burse", "bursa"} & token_set and {"2", "cumulare", "beneficia", "conditii", "eligibil"} & token_set:
        scores["regulamente"] += 8
    if is_volunteering_credit_query(question_text, token_set):
        scores["regulamente"] += 12
        scores["studenti"] += 8
        if not ({"admitere", "inscriere", "candidat"} & token_set or "dosar de admitere" in question_text):
            scores["admitere"] -= 10
    if _is_housing_document_question(token_set):
        scores["regulamente"] += 10
        scores["studenti"] += 8
        scores["admitere"] -= 6
    elif _is_social_document_question(token_set):
        scores["regulamente"] += 10
        scores["burse"] += 8
        scores["studenti"] += 4
        scores["admitere"] -= 6
    if any(phrase in question_text for phrase in POLICY_PHRASES):
        scores["regulamente"] += 5

    return scores


def detect_intent(question: str) -> str:
    tokens = tokenize(question)
    scores = _score_intents(question, tokens)
    best_intent = max(scores, key=scores.get)
    return best_intent if scores[best_intent] > 0 else "general"


def detect_policy_question(question: str, intent: str) -> bool:
    question_text = normalize(question)
    tokens = set(tokenize(question_text))

    if intent == "regulamente":
        return True
    if is_volunteering_credit_query(question_text, tokens):
        return True
    if any(phrase in question_text for phrase in POLICY_PHRASES):
        return True
    if {"regulament", "regulamente", "metodologie", "procedura", "proceduri"} & tokens:
        return True
    if _is_housing_document_question(tokens) or _is_social_document_question(tokens):
        return True
    if {"burse", "bursa"} & tokens and {"2", "cumulare", "beneficia", "conditii", "eligibil"} & tokens:
        return True

    return False


def is_volunteering_credit_query(question_text: str, tokens: Iterable[str]) -> bool:
    token_set = set(tokens)
    has_volunteering = bool(set(VOLUNTEERING_TERMS) & token_set) or "voluntariat" in question_text
    has_credit_or_submission = bool(set(VOLUNTEERING_CREDIT_TERMS + SUBMISSION_TERMS) & token_set)
    return has_volunteering and has_credit_or_submission
