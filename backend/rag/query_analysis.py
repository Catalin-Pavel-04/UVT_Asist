from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Iterable

from core.config import env_bool, env_int
from ollama_client import ask_ollama_json
from rag.constants import (
    INTENT_KEYWORDS,
    INTENT_PAGE_TYPES,
    OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS,
    OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS,
)
from rag.intent_detection import (
    _is_housing_document_question,
    _is_social_document_question,
    _score_intents,
    is_volunteering_credit_query,
)
from rag.text_normalization import normalize, tokenize

VALID_INTENTS = {"orar", "burse", "contact", "admitere", "regulamente", "studenti", "general"}
QUERY_REWRITE_CACHE_TTL = env_int("QUERY_REWRITE_CACHE_TTL", "600", minimum=0, strict=False)
_QUERY_REWRITE_CACHE: dict[str, tuple[float, dict]] = {}


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
    keywords: tuple[str, ...]
    faculty_hint: str
    requires_clarification: bool
    clarification_reason: str
    rewrite_source: str

    def to_dict(self) -> dict:
        return asdict(self)


def query_analysis_enabled() -> bool:
    return env_bool("OLLAMA_QUERY_ANALYSIS_ENABLED", "true")


def _technical_cache_key(question: str) -> str:
    return normalize(question)[:1200]


def _cached_rewrite(question: str) -> dict | None:
    if QUERY_REWRITE_CACHE_TTL <= 0:
        return None
    cache_key = _technical_cache_key(question)
    cached = _QUERY_REWRITE_CACHE.get(cache_key)
    if not cached:
        return None
    expires_at, value = cached
    if expires_at < time.time():
        _QUERY_REWRITE_CACHE.pop(cache_key, None)
        return None
    return dict(value)


def _store_cached_rewrite(question: str, value: dict) -> None:
    if QUERY_REWRITE_CACHE_TTL <= 0:
        return
    cache_key = _technical_cache_key(question)
    _QUERY_REWRITE_CACHE[cache_key] = (time.time() + QUERY_REWRITE_CACHE_TTL, dict(value))


def build_page_type_preferences(intent: str, is_policy_question: bool, tokens: Iterable[str]) -> tuple[str, ...]:
    token_set = set(tokens)
    if is_volunteering_credit_query(" ".join(token_set), token_set):
        return ("regulamente", "studenti", "general")
    if _is_housing_document_question(token_set):
        return ("regulamente", "studenti", "general")
    if _is_social_document_question(token_set):
        return ("regulamente", "burse", "studenti", "general")
    if is_policy_question:
        if {"burse", "bursa"} & token_set:
            return ("regulamente", "burse", "studenti", "general")
        if intent == "admitere":
            return ("regulamente", "admitere", "general")
        return ("regulamente", "studenti", "general", "burse")

    return INTENT_PAGE_TYPES.get(intent, INTENT_PAGE_TYPES["general"])


def expand_query_tokens(tokens: Iterable[str], intent: str, is_policy_question: bool) -> tuple[str, ...]:
    """Add deterministic retrieval hints after Ollama has interpreted the query."""
    expanded = list(dict.fromkeys(tokens))
    token_set = set(expanded)

    intent_terms = {
        "orar": ("orar", "orare"),
        "burse": ("bursa", "burse", "burselor"),
        "contact": ("contact", "secretariat", "telefon", "email", "adresa"),
        "admitere": ("admitere", "inscriere", "candidat", "dosar"),
        "regulamente": ("regulament", "regulamente", "metodologie", "procedura", "anexa"),
        "studenti": ("student", "studenti", "studentweb", "cazare", "camin", "camine", "taxe", "calendar"),
    }

    for token in intent_terms.get(intent, ()):
        if token not in expanded:
            expanded.append(token)

    if is_policy_question:
        for token in ("regulament", "metodologie", "procedura", "anexa", "conditii", "eligibil"):
            if token not in expanded:
                expanded.append(token)

    if is_volunteering_credit_query(" ".join(expanded), set(expanded)):
        for token in ("voluntariat", "credite", "portofoliu", "formular", "raport", "adeverinta"):
            if token not in expanded:
                expanded.append(token)

    if _is_housing_document_question(token_set):
        for token in ("cazare", "camin", "camine", "documente", "justificativ", "social"):
            if token not in expanded:
                expanded.append(token)

    if _is_social_document_question(token_set) and not _is_housing_document_question(token_set):
        for token in ("burse", "bursa", "social", "documente", "justificativ", "venituri"):
            if token not in expanded:
                expanded.append(token)

    return tuple(dict.fromkeys(expanded))


def analyze_query_deterministic(question: str) -> QueryAnalysis:
    return raw_fallback_query_analysis(question)


def raw_fallback_query_analysis(question: str) -> QueryAnalysis:
    normalized_question = normalize(question)
    tokens = tuple(tokenize(normalized_question))
    page_type_preferences = build_page_type_preferences("general", False, tokens)
    return QueryAnalysis(
        original_question=question,
        normalized_question=normalized_question,
        corrected_question=normalized_question,
        tokens=tokens,
        expanded_tokens=tokens,
        intent="general",
        is_policy_question=False,
        page_type_preferences=page_type_preferences,
        corrections=(),
        keywords=tokens[:OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS],
        faculty_hint="",
        requires_clarification=False,
        clarification_reason="",
        rewrite_source="raw_fallback",
    )


def _query_analysis_allowed_token(token: str, original_tokens: set[str] | None = None) -> bool:
    return bool(token and len(token) <= 48)


def _validated_query_analysis_tokens(values, original_tokens: set[str] | None = None) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []

    tokens: list[str] = []
    for value in values:
        for token in tokenize(str(value)):
            if _query_analysis_allowed_token(token, original_tokens):
                tokens.append(token)
            if len(tokens) >= OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS:
                break
        if len(tokens) >= OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS:
            break
    return list(dict.fromkeys(tokens))


def _validated_query_analysis_intents(values) -> set[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return set()
    return {normalize(str(value)) for value in values if normalize(str(value)) in VALID_INTENTS}


def _validated_corrected_question(value, base: QueryAnalysis) -> str:
    corrected = normalize(str(value or "")).strip()
    if len(corrected) < 2 or len(corrected) > 260:
        return base.corrected_question
    return corrected


def _validated_bool(value) -> bool:
    return value is True


def _validated_text(value, max_chars: int = 220) -> str:
    return normalize(str(value or "")).strip()[:max_chars]


def _validated_ollama_payload(value) -> dict | None:
    if not isinstance(value, dict):
        return None

    intent = normalize(str(value.get("intent") or "general"))
    if intent not in VALID_INTENTS:
        intent = "general"

    keywords_raw = value.get("keywords")
    if isinstance(keywords_raw, str):
        keywords_raw = [keywords_raw]
    if not isinstance(keywords_raw, list):
        keywords_raw = []

    return {
        "corrected_question": str(value.get("corrected_question") or ""),
        "intent": intent,
        "is_policy_question": value.get("is_policy_question") is True,
        "keywords": [str(item) for item in keywords_raw[:OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS]],
        "faculty_hint": str(value.get("faculty_hint") or ""),
        "requires_clarification": value.get("requires_clarification") is True,
        "clarification_reason": str(value.get("clarification_reason") or ""),
    }


def _build_ollama_query_analysis_prompt(question: str, base: QueryAnalysis | None = None) -> tuple[str, str]:
    system_prompt = (
        "Esti un modul local de analiza lingvistica pentru un asistent UVT. "
        "Nu raspunde la intrebare. Nu alege surse. Nu inventa informatii administrative. "
        "Returneaza exclusiv JSON valid, fara markdown."
    )
    user_prompt = f"""
Analizeaza intrebarea si returneaza exclusiv un obiect JSON cu schema:
{{
  "corrected_question": "string",
  "intent": "orar|burse|contact|admitere|regulamente|studenti|general",
  "is_policy_question": true,
  "keywords": ["string"],
  "faculty_hint": "string",
  "requires_clarification": false,
  "clarification_reason": "string"
}}

Reguli:
- Nu raspunde la intrebare.
- Nu alege surse, URL-uri sau pagini.
- Nu schimba sensul intrebarii.
- Corecteaza typo-uri, abrevieri si formulari neclare doar la nivel de intrebare.
- Pentru "info", "fmi", "fac de info", "informatica", seteaza faculty_hint="info".
- Pentru "program", daca nu este clar daca inseamna orar, secretariat sau program de studii,
  seteaza requires_clarification=true.
- Pentru burse, cumul, regulamente, metodologii, proceduri, dosare sau acte,
  marcheaza is_policy_question=true.
- Pentru intrebari vagi, seteaza requires_clarification=true si explica scurt de ce.
- Keywords trebuie sa fie termeni scurti utili pentru cautare, fara propozitii.

Exemple de comportament:
- "unde gasesc orrarul la info" => corrected_question include "orar", intent="orar", faculty_hint="info".
- "secreteriat info" => corrected_question include "secretariat", intent="contact", faculty_hint="info".
- "pot primi doua burse?" => intent="regulamente", is_policy_question=true, keywords include "burse" si "cumulare".
- "program" => requires_clarification=true.

Intrebare originala:
{question}
""".strip()
    return system_prompt, user_prompt


def request_ollama_query_analysis(question: str, base: QueryAnalysis | None = None) -> dict | None:
    cached = _cached_rewrite(question)
    if cached is not None:
        return cached

    system_prompt, user_prompt = _build_ollama_query_analysis_prompt(question, base)
    try:
        suggestion = ask_ollama_json(
            system_prompt,
            user_prompt,
            timeout_seconds=OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS,
            num_predict=260,
        )
    except Exception:
        return None

    validated = _validated_ollama_payload(suggestion)
    if validated is not None:
        _store_cached_rewrite(question, validated)
    return validated


def merge_ollama_query_analysis(question: str, base: QueryAnalysis, suggestion: dict | None) -> QueryAnalysis:
    if not isinstance(suggestion, dict):
        return base

    corrected_question = _validated_corrected_question(suggestion.get("corrected_question"), base)
    tokens = tuple(tokenize(corrected_question)) or base.tokens
    keywords = tuple(_validated_query_analysis_tokens(suggestion.get("keywords"), set(tokens)))

    intent = normalize(str(suggestion.get("intent") or "general"))
    if intent not in VALID_INTENTS:
        intent = "general"

    is_policy_question = _validated_bool(suggestion.get("is_policy_question"))
    original_tokens = tuple(tokenize(base.original_question))
    combined_tokens = tuple(dict.fromkeys([*tokens, *keywords, *original_tokens]))
    page_type_preferences = build_page_type_preferences(intent, is_policy_question, combined_tokens)
    expanded_tokens = expand_query_tokens(combined_tokens, intent, is_policy_question)
    faculty_hint = _validated_text(suggestion.get("faculty_hint"), 48)
    requires_clarification = _validated_bool(suggestion.get("requires_clarification"))
    clarification_reason = _validated_text(suggestion.get("clarification_reason"), 240)

    corrections: list[str] = []
    if corrected_question != base.corrected_question:
        corrections.append("ollama_query_rewrite")
    if keywords:
        corrections.append("ollama_keywords")
    if requires_clarification:
        corrections.append("ollama_clarification")

    return QueryAnalysis(
        original_question=question,
        normalized_question=base.normalized_question,
        corrected_question=corrected_question,
        tokens=tokens,
        expanded_tokens=expanded_tokens,
        intent=intent,
        is_policy_question=is_policy_question,
        page_type_preferences=page_type_preferences,
        corrections=tuple(corrections),
        keywords=keywords,
        faculty_hint=faculty_hint,
        requires_clarification=requires_clarification,
        clarification_reason=clarification_reason,
        rewrite_source="ollama",
    )


def analyze_query(question: str) -> QueryAnalysis:
    base = raw_fallback_query_analysis(question)
    if not query_analysis_enabled():
        return base
    suggestion = request_ollama_query_analysis(question, base)
    return merge_ollama_query_analysis(question, base, suggestion)
