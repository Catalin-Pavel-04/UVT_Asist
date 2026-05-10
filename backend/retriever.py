from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import get_close_matches
from typing import Iterable
from urllib.parse import urlparse

from page_index import is_generic_page_title

INTENT_TO_PAGE_TYPES = {
    "orar": ("orar", "studenti", "general"),
    "burse": ("burse", "studenti", "regulamente", "general"),
    "contact": ("contact", "studenti", "general"),
    "admitere": ("admitere", "general"),
    "regulamente": ("regulamente", "studenti", "general"),
    "studenti": ("studenti", "general"),
    "general": ("general", "studenti", "contact", "burse", "admitere", "orar", "regulamente"),
}

INTENT_KEYWORDS = {
    "orar": ("orar", "orare", "orarul", "orarului"),
    "burse": ("bursa", "burse", "bursier", "bursieri"),
    "contact": ("contact", "secretariat", "secretar", "email", "telefon", "program cu publicul"),
    "admitere": ("admitere", "inscriere", "inscrieri", "dosar", "concurs"),
    "regulamente": ("regulament", "regulamente", "metodologie", "metodologii", "procedura", "proceduri", "anexa"),
    "studenti": ("student", "studenti", "cazare", "taxa", "taxe", "camin"),
}

PAGE_TYPE_HINTS = {
    "orar": ("/orare", "/orar", "orar"),
    "burse": ("/burse", "bursa", "burse"),
    "contact": ("/contact", "/secretariat", "contact", "secretariat"),
    "admitere": ("/admitere", "/inscriere", "admitere", "inscriere"),
    "regulamente": ("/regulamente", "/regulament", "/metodologii", "/metodologie", "/proceduri", "/procedura", "regulament", "metodologie", "procedura"),
    "studenti": ("/studenti", "studenti"),
}

COMMON_TEXT_PATTERNS = (
    (r"\binformatia\b", "informatica"),
    (r"\binformatici\b", "informatica"),
    (r"\binformaticii\b", "informatica"),
    (r"\bfmi\b", "informatica"),
    (r"\bfac(?:ultatea)?(?:\s+de)?\s+info(?:rmatica)?\b", "informatica"),
    (r"\bsecretaruat\b", "secretariat"),
    (r"\bsecreteriat\b", "secretariat"),
    (r"\bsecretarait\b", "secretariat"),
    (r"\bsecretarait\b", "secretariat"),
    (r"\bbursw\b", "burse"),
    (r"\bbursae\b", "burse"),
    (r"\bbursae\b", "burse"),
    (r"\badmiterw\b", "admitere"),
    (r"\badmietere\b", "admitere"),
    (r"\boraru\b", "orar"),
    (r"\borrar(?:ul)?\b", "orar"),
    (r"\borra\b", "orar"),
    (r"\bmetodolgie\b", "metodologie"),
    (r"\bregulam(?:e)?nt\b", "regulament"),
    (r"\bprocedrura\b", "procedura"),
    (r"\bcumuleaz[ae]\b", "cumulare"),
)

STOPWORDS = {
    "a", "ai", "al", "am", "ar", "as", "asa", "at", "au", "ca", "care", "ce", "cea", "cele", "cel",
    "cei", "cum", "cu", "de", "despre", "din", "doar", "este", "fi", "fie", "in", "la", "ma", "mai",
    "mi", "o", "pe", "pot", "poate", "sa", "sau", "se", "si", "sunt", "un", "una", "unde", "vreau",
}

DOMAIN_VOCABULARY = {
    "admitere",
    "burse",
    "bursa",
    "contact",
    "secretariat",
    "studenti",
    "student",
    "orar",
    "orare",
    "regulament",
    "regulamente",
    "metodologie",
    "metodologii",
    "procedura",
    "proceduri",
    "inscriere",
    "inscrieri",
    "informatica",
    "facultate",
    "program",
    "uvt",
    "cumulare",
    "cumulare",
    "beneficia",
    "beneficieze",
    "beneficii",
    "bursei",
    "informatii",
    "informatie",
}

CORRECTION_SKIP_TOKENS = {
    "informatii",
    "informatie",
    "detalii",
    "general",
}

POLICY_PATTERNS = (
    "este posibil",
    "se poate",
    "pot beneficia",
    "poate beneficia",
    "beneficiezi de",
    "beneficia de",
    "beneficieze de",
    "pot primi",
    "cumulare",
    "se cumuleaza",
    "doua burse",
    "2 burse",
    "regulament",
    "metodologie",
    "procedura",
    "eligibil",
    "conditii",
)

_PREPARED_INDEX_CACHE = None
_PREPARED_INDEX_SIGNATURE = None


@dataclass(frozen=True)
class QueryAnalysis:
    original_question: str
    normalized_question: str
    corrected_question: str
    tokens: tuple[str, ...]
    expanded_tokens: tuple[str, ...]
    intent: str
    is_policy_question: bool
    page_type_preferences: tuple[str, ...]
    corrections: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_common_terms(text: str) -> str:
    normalized = f" {text} "

    for pattern, replacement in COMMON_TEXT_PATTERNS:
        normalized = re.sub(pattern, replacement, normalized)

    return re.sub(r"\s+", " ", normalized).strip()


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text).lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalize_common_terms(normalized)


def tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    normalized = normalize(text)
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    tokens = [token.strip("-") for token in cleaned.split() if token.strip("-")]
    if remove_stopwords:
        tokens = [token for token in tokens if token not in STOPWORDS and len(token) >= 2]
    return tokens


def correct_query_terms(question: str) -> tuple[str, list[str]]:
    normalized = normalize(question)
    corrected_tokens = []
    corrections = []

    for token in tokenize(normalized, remove_stopwords=False):
        replacement = token
        if token in CORRECTION_SKIP_TOKENS:
            corrected_tokens.append(token)
            continue

        if token not in DOMAIN_VOCABULARY and len(token) >= 4 and not token.isdigit():
            matches = get_close_matches(token, DOMAIN_VOCABULARY, n=1, cutoff=0.84)
            if matches:
                replacement = matches[0]

        corrected_tokens.append(replacement)
        if replacement != token:
            corrections.append(f"{token}->{replacement}")

    corrected_text = " ".join(corrected_tokens).strip()
    return corrected_text or normalized, corrections


def detect_intent(question: str) -> str:
    question_text = normalize(question)
    scores = {intent: 0 for intent in INTENT_KEYWORDS}

    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in question_text:
                scores[intent] += 2

    if "program" in question_text and ("secretariat" in question_text or "contact" in question_text):
        scores["contact"] += 2
    if any(term in question_text for term in ("se poate", "este posibil", "cumulare")):
        scores["regulamente"] += 3
    if "burse" in question_text and any(term in question_text for term in ("doua", "2", "cumulare", "beneficia")):
        scores["regulamente"] += 4

    best_intent = max(scores, key=scores.get)
    return best_intent if scores[best_intent] > 0 else "general"


def detect_policy_question(question: str, intent: str | None = None) -> bool:
    normalized_question = normalize(question)
    if intent == "regulamente":
        return True

    if any(pattern in normalized_question for pattern in POLICY_PATTERNS):
        return True

    if "burse" in normalized_question and any(token in normalized_question for token in ("doua", "2", "cumul", "beneficia")):
        return True

    return False


def build_page_type_preferences(intent: str, is_policy_question: bool) -> tuple[str, ...]:
    if is_policy_question:
        if intent == "burse":
            return ("regulamente", "burse", "studenti", "general")
        if intent == "contact":
            return ("contact", "general")
        if intent == "admitere":
            return ("regulamente", "admitere", "general")
        return ("regulamente", "studenti", "general", "burse")

    return INTENT_TO_PAGE_TYPES.get(intent, INTENT_TO_PAGE_TYPES["general"])


def expand_query_tokens(tokens: Iterable[str], intent: str, is_policy_question: bool) -> list[str]:
    expanded = list(tokens)

    synonyms = {
        "orar": ("orar", "orare"),
        "burse": ("bursa", "burse"),
        "contact": ("contact", "secretariat", "telefon", "email"),
        "admitere": ("admitere", "inscriere"),
        "regulamente": ("regulament", "regulamente", "metodologie", "procedura"),
        "studenti": ("studenti", "student"),
    }

    for synonym in synonyms.get(intent, ()):
        if synonym not in expanded:
            expanded.append(synonym)

    if is_policy_question:
        for synonym in ("regulament", "metodologie", "procedura", "cumulare"):
            if synonym not in expanded:
                expanded.append(synonym)

    return expanded


def analyze_query(question: str) -> QueryAnalysis:
    normalized_question = normalize(question)
    corrected_question, corrections = correct_query_terms(question)
    intent = detect_intent(corrected_question or normalized_question)
    is_policy_question = detect_policy_question(corrected_question or normalized_question, intent=intent)
    tokens = tuple(tokenize(corrected_question or normalized_question))
    expanded_tokens = tuple(expand_query_tokens(tokens, intent, is_policy_question))
    page_type_preferences = build_page_type_preferences(intent, is_policy_question)

    return QueryAnalysis(
        original_question=question,
        normalized_question=normalized_question,
        corrected_question=corrected_question or normalized_question,
        tokens=tokens,
        expanded_tokens=expanded_tokens,
        intent=intent,
        is_policy_question=is_policy_question,
        page_type_preferences=page_type_preferences,
        corrections=tuple(corrections),
    )


def _prepare_chunk(chunk: dict) -> dict:
    title = str(chunk.get("title") or "")
    url = str(chunk.get("url") or "")
    chunk_text = str(chunk.get("chunk_text") or chunk.get("chunk") or "")

    title_tokens = tokenize(title)
    url_tokens = tokenize(url)
    text_tokens = tokenize(chunk_text)
    combined_tokens = title_tokens + url_tokens + text_tokens

    return {
        **chunk,
        "_title_norm": normalize(title),
        "_url_norm": normalize(url),
        "_text_norm": normalize(chunk_text),
        "_title_tokens": title_tokens,
        "_url_tokens": url_tokens,
        "_text_tokens": text_tokens,
        "_title_counter": Counter(title_tokens),
        "_url_counter": Counter(url_tokens),
        "_text_counter": Counter(text_tokens),
        "_token_set": set(combined_tokens),
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

    raw_chunks = index_document.get("chunks", [])
    prepared_chunks = [_prepare_chunk(chunk) for chunk in raw_chunks if isinstance(chunk, dict) and chunk.get("chunk_text")]
    document_frequency = Counter()

    for chunk in prepared_chunks:
        document_frequency.update(chunk["_token_set"])

    total_chunks = max(1, len(prepared_chunks))
    inverse_document_frequency = {
        token: math.log(1 + (total_chunks - frequency + 0.5) / (frequency + 0.5))
        for token, frequency in document_frequency.items()
    }

    prepared_index = {
        "signature": signature,
        "chunks": prepared_chunks,
        "idf": inverse_document_frequency,
    }
    _PREPARED_INDEX_CACHE = prepared_index
    _PREPARED_INDEX_SIGNATURE = signature
    return prepared_index


def _field_overlap_score(query_tokens: Iterable[str], counter: Counter, idf: dict[str, float], weight: float) -> float:
    score = 0.0

    for token in query_tokens:
        score += idf.get(token, 0.6) * counter.get(token, 0) * weight

    return score


def _metadata_boost(prepared_chunk: dict, analysis: QueryAnalysis, selected_faculty: str) -> tuple[float, list[str]]:
    score = 0.0
    signals: list[str] = []
    page_type = prepared_chunk.get("page_type") or "general"
    faculty_id = prepared_chunk.get("faculty_id") or "uvt"
    title_norm = prepared_chunk["_title_norm"]
    url_norm = prepared_chunk["_url_norm"]
    path = (urlparse(prepared_chunk.get("url", "")).path or "/").rstrip("/") or "/"

    if faculty_id == selected_faculty:
        score += 26
        signals.append("faculty_exact")
    elif faculty_id == "uvt":
        boost = 20 if analysis.is_policy_question else 8
        score += boost
        signals.append("faculty_uvt")
    elif selected_faculty != "uvt":
        score -= 42
    elif analysis.is_policy_question:
        score -= 28
        signals.append("policy_other_faculty_penalty")

    if page_type in analysis.page_type_preferences:
        position = analysis.page_type_preferences.index(page_type)
        page_boost = max(6, 20 - position * 5)
        score += page_boost
        signals.append(f"page_type:{page_type}")
    elif page_type == "general":
        score += 2
    else:
        score -= 4

    for hint in PAGE_TYPE_HINTS.get(analysis.intent, ()):
        if hint in url_norm or hint in title_norm:
            score += 10
            signals.append(f"hint:{analysis.intent}")
            break

    if analysis.intent == "contact" and any(term in f"{title_norm} {url_norm}" for term in ("secretariat", "contact")):
        score += 12
        signals.append("contact_specific")
    if analysis.intent == "orar" and any(term in f"{title_norm} {url_norm}" for term in ("orare", "orar")):
        score += 14
        signals.append("orar_specific")
    if analysis.intent == "admitere" and "admitere" in f"{title_norm} {url_norm}":
        score += 14
        signals.append("admitere_specific")
    if analysis.intent == "burse" and "burs" in f"{title_norm} {url_norm}":
        score += 10
        signals.append("burse_specific")

    if analysis.is_policy_question:
        combined_norm = f"{title_norm} {url_norm} {prepared_chunk['_text_norm']}"
        if page_type == "regulamente":
            score += 34
            signals.append("policy_regulations")
        if faculty_id == "uvt":
            score += 18
            signals.append("policy_uvt")
        if any(term in f"{title_norm} {url_norm}" for term in ("regulament", "metodolog", "procedur")):
            score += 18
            signals.append("policy_title")
        if any(token in analysis.expanded_tokens for token in ("burse", "bursa")):
            if "burs" in combined_norm:
                score += 14
                signals.append("policy_topic_burse")
            else:
                score -= 16
                signals.append("policy_topic_penalty")

    if path == "/" or is_generic_page_title(prepared_chunk.get("title", "")):
        score -= 20
        signals.append("generic_penalty")

    return score, signals


def score_chunk_candidate(
    prepared_chunk: dict,
    analysis: QueryAnalysis,
    selected_faculty: str,
    idf: dict[str, float],
) -> dict:
    query_tokens = analysis.expanded_tokens or analysis.tokens
    lexical_score = 0.0
    lexical_score += _field_overlap_score(query_tokens, prepared_chunk["_text_counter"], idf, 1.6)
    lexical_score += _field_overlap_score(query_tokens, prepared_chunk["_title_counter"], idf, 3.2)
    lexical_score += _field_overlap_score(query_tokens, prepared_chunk["_url_counter"], idf, 2.8)

    text_norm = prepared_chunk["_text_norm"]
    title_norm = prepared_chunk["_title_norm"]
    url_norm = prepared_chunk["_url_norm"]

    for token in analysis.tokens:
        if token in title_norm:
            lexical_score += 2.8
        elif token in url_norm:
            lexical_score += 2.2
        elif token in text_norm:
            lexical_score += 1.4

    metadata_score, signals = _metadata_boost(prepared_chunk, analysis, selected_faculty)
    total_score = max(0.0, lexical_score + metadata_score)

    return {
        "chunk_id": prepared_chunk.get("chunk_id"),
        "faculty_id": prepared_chunk.get("faculty_id", "uvt"),
        "page_type": prepared_chunk.get("page_type", "general"),
        "title": prepared_chunk.get("title", prepared_chunk.get("url", "")),
        "url": prepared_chunk.get("url", ""),
        "chunk_text": prepared_chunk.get("chunk_text", ""),
        "last_indexed": prepared_chunk.get("last_indexed"),
        "retrieval_score": round(total_score, 3),
        "match_signals": signals,
    }


def select_diverse_chunks(scored_chunks: list[dict], top_k: int, max_chunks_per_url: int = 1) -> list[dict]:
    selected = []
    url_counts: dict[str, int] = {}

    for chunk in scored_chunks:
        url = chunk.get("url", "")
        current_count = url_counts.get(url, 0)
        if current_count >= max_chunks_per_url:
            continue

        selected.append(chunk)
        url_counts[url] = current_count + 1

        if len(selected) >= top_k:
            break

    return selected


def rank_index(question: str, index_document: dict, selected_faculty: str, top_k: int = 6) -> dict:
    analysis = analyze_query(question)
    prepared_index = prepare_index(index_document)
    scored = []

    for prepared_chunk in prepared_index["chunks"]:
        candidate_faculty = prepared_chunk.get("faculty_id", "uvt")
        if selected_faculty != "uvt" and candidate_faculty not in {selected_faculty, "uvt"}:
            continue

        scored_chunk = score_chunk_candidate(
            prepared_chunk,
            analysis,
            selected_faculty,
            prepared_index["idf"],
        )
        if scored_chunk["retrieval_score"] > 0:
            scored.append(scored_chunk)

    if analysis.is_policy_question:
        preferred_scored = [
            item for item in scored
            if item.get("faculty_id") == "uvt" or item.get("page_type") == "regulamente"
        ]
        if preferred_scored:
            scored = preferred_scored

    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    top_chunks = select_diverse_chunks(scored, top_k=top_k)
    confidence = compute_confidence(top_chunks, analysis)

    return {
        "analysis": analysis.to_dict(),
        "chunks": top_chunks,
        "confidence": confidence["label"],
        "confidence_score": confidence["score"],
        "confidence_reason": confidence["reason"],
    }


def rank_runtime_chunks(chunks: list[dict], question: str, selected_faculty: str, idf: dict[str, float] | None = None, top_k: int = 4) -> dict:
    analysis = analyze_query(question)
    prepared_chunks = [_prepare_chunk(chunk) for chunk in chunks if chunk.get("chunk_text")]
    scored = []

    for prepared_chunk in prepared_chunks:
        scored_chunk = score_chunk_candidate(prepared_chunk, analysis, selected_faculty, idf or {})
        if scored_chunk["retrieval_score"] > 0:
            scored.append(scored_chunk)

    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    top_chunks = select_diverse_chunks(scored, top_k=top_k)
    confidence = compute_confidence(top_chunks, analysis)

    return {
        "analysis": analysis.to_dict(),
        "chunks": top_chunks,
        "confidence": confidence["label"],
        "confidence_score": confidence["score"],
        "confidence_reason": confidence["reason"],
    }


def compute_confidence(scored_chunks: list[dict], analysis: QueryAnalysis | dict | None = None) -> dict:
    if not scored_chunks:
        return {
            "label": "low",
            "score": 10,
            "reason": "Nu au fost gasite fragmente oficiale suficient de relevante.",
        }

    analysis_dict = analysis.to_dict() if isinstance(analysis, QueryAnalysis) else (analysis or {})
    best_score = float(scored_chunks[0].get("retrieval_score", 0.0))
    second_score = float(scored_chunks[1].get("retrieval_score", 0.0)) if len(scored_chunks) > 1 else 0.0
    unique_pages = len({chunk.get("url") for chunk in scored_chunks[:3] if chunk.get("url")})
    unique_signals = len(set(scored_chunks[0].get("match_signals", [])))

    numeric_score = int(min(100, best_score * 2.1 + second_score * 0.45 + unique_pages * 5 + unique_signals * 4))

    if analysis_dict.get("is_policy_question") and scored_chunks[0].get("page_type") == "regulamente":
        numeric_score = min(100, numeric_score + 6)

    if numeric_score >= 78:
        label = "high"
    elif numeric_score >= 52:
        label = "medium"
    else:
        label = "low"

    if label == "high":
        reason = "Sursele corespund bine pe facultate, tip de pagina si continut."
    elif label == "medium":
        reason = "Exista surse oficiale relevante, dar potrivirea nu este perfecta."
    else:
        reason = "Au fost gasite doar dovezi partiale sau prea generale."

    return {
        "label": label,
        "score": numeric_score,
        "reason": reason,
    }
