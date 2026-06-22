from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from rag.query_analysis import QueryAnalysis
from rag.text_normalization import normalize

def _counter(tokens: Iterable[str]) -> Counter:
    return Counter(tokens)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _contains_token(text: str, token: str) -> bool:
    return bool(re.search(rf"\b{re.escape(token)}\b", text))


def _field_overlap_score(tokens: Iterable[str], counter: Counter, idf: dict[str, float], weight: float) -> float:
    return sum(idf.get(token, 0.6) * counter.get(token, 0) * weight for token in tokens)


def _lexical_score(chunk: dict, analysis: QueryAnalysis, idf: dict[str, float]) -> tuple[float, list[str]]:
    signals: list[str] = []
    score = 0.0

    score += _field_overlap_score(analysis.tokens, chunk["_title_counter"], idf, 4.0)
    score += _field_overlap_score(analysis.tokens, chunk["_url_counter"], idf, 3.4)
    score += _field_overlap_score(analysis.tokens, chunk["_text_counter"], idf, 1.8)

    expanded_only = [token for token in analysis.expanded_tokens if token not in analysis.tokens]
    score += _field_overlap_score(expanded_only, chunk["_title_counter"], idf, 1.8)
    score += _field_overlap_score(expanded_only, chunk["_url_counter"], idf, 1.5)
    score += _field_overlap_score(expanded_only, chunk["_text_counter"], idf, 0.8)

    haystack = f"{chunk['_title_norm']} {chunk['_url_norm']} {chunk['_text_norm']}"
    matched_tokens = [token for token in analysis.tokens if token in chunk["_token_set"] or token in haystack]
    if matched_tokens:
        signals.append(f"lexical:{len(set(matched_tokens))}")

    if analysis.tokens and all(token in haystack for token in analysis.tokens):
        score += 10
        signals.append("all_terms")

    corrected_phrase = normalize(analysis.corrected_question)
    if len(corrected_phrase) >= 12 and corrected_phrase in haystack:
        score += 18
        signals.append("phrase")

    return score, signals
