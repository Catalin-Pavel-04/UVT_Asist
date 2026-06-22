from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from core.config import env_bool
from ollama_client import ask_ollama_json
from rag.constants import (
    CUMULATION_TERMS,
    DOCUMENT_REQUEST_TERMS,
    DOMAIN_VOCABULARY,
    INTENT_KEYWORDS,
    INTENT_PAGE_TYPES,
    OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS,
    OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS,
    POLICY_DOCUMENT_TERMS,
    SCHOLARSHIP_TERMS,
    SOCIAL_CONTEXT_TERMS,
    SUBMISSION_TERMS,
    VOLUNTEERING_CREDIT_TERMS,
    VOLUNTEERING_TERMS,
)
from rag.intent_detection import (
    _has_housing_context,
    _is_housing_document_question,
    _is_social_document_question,
    _score_intents,
    detect_intent,
    detect_policy_question,
    is_volunteering_credit_query,
)
from rag.text_normalization import correct_query_terms, normalize, tokenize

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
    expanded = list(dict.fromkeys(tokens))
    original_token_set = set(expanded)
    synonyms = {
        "orar": ("orar", "orare"),
        "burse": ("bursa", "burse", "burselor"),
        "contact": ("contact", "secretariat", "telefon", "email", "adresa"),
        "admitere": ("admitere", "inscriere", "candidat", "dosar"),
        "regulamente": ("regulament", "regulamente", "metodologie", "procedura", "anexa"),
        "studenti": (
            "student", "studenti", "studentweb", "cazare", "camin", "camine", "taxe",
            "calendar", "structura", "universitar", "semestru", "sesiune", "vacante", "saptamani",
        ),
    }

    for token in synonyms.get(intent, ()):
        if token not in expanded:
            expanded.append(token)

    expanded_set = set(expanded)
    if is_volunteering_credit_query(" ".join(expanded), expanded_set):
        for token in (
            "voluntariat",
            "credite",
            "transferabile",
            "portofoliu",
            "formular",
            "raport",
            "adeverinta",
            "evaluare",
            "recunoastere",
        ):
            if token not in expanded:
                expanded.append(token)

    if _is_housing_document_question(expanded_set):
        for token in ("cazare", "camin", "camine", "documente", "justificativ", "social", "orfan", "monoparentala"):
            if token not in expanded:
                expanded.append(token)

    if _is_social_document_question(expanded_set) and not _has_housing_context(expanded_set):
        for token in (
            "burse",
            "bursa",
            "social",
            "sociale",
            "sprijin",
            "documente",
            "justificativ",
            "orfan",
            "monoparentala",
            "familie",
            "venituri",
        ):
            if token not in expanded:
                expanded.append(token)

    if is_policy_question:
        for token in ("regulament", "metodologie", "procedura", "anexa", "conditii", "eligibil"):
            if token not in expanded:
                expanded.append(token)
        social_document_question = _is_social_document_question(expanded)
        explicit_cumulation_question = bool({"2", "cumulare", "beneficia"} & original_token_set)
        if {"burse", "bursa"} & set(expanded) and (explicit_cumulation_question or not social_document_question):
            for token in ("bursa", "burse", "burselor", "cumulare", "beneficia"):
                if token not in expanded:
                    expanded.append(token)

    return tuple(expanded)


def analyze_query_deterministic(question: str) -> QueryAnalysis:
    normalized_question = normalize(question)
    corrected_question, corrections = correct_query_terms(question)
    intent = detect_intent(corrected_question)
    is_policy_question = detect_policy_question(corrected_question, intent)
    tokens = tuple(tokenize(corrected_question))
    page_type_preferences = build_page_type_preferences(intent, is_policy_question, tokens)
    expanded_tokens = expand_query_tokens(tokens, intent, is_policy_question)

    return QueryAnalysis(
        original_question=question,
        normalized_question=normalized_question,
        corrected_question=corrected_question,
        tokens=tokens,
        expanded_tokens=expanded_tokens,
        intent=intent,
        is_policy_question=is_policy_question,
        page_type_preferences=page_type_preferences,
        corrections=tuple(corrections),
    )


def query_analysis_enabled() -> bool:
    return env_bool("OLLAMA_QUERY_ANALYSIS_ENABLED", "false")


def _query_analysis_allowed_token(token: str, original_tokens: set[str]) -> bool:
    if token.isdigit() or token in original_tokens:
        return True

    if original_tokens & set(VOLUNTEERING_TERMS + VOLUNTEERING_CREDIT_TERMS):
        allowed = set(VOLUNTEERING_TERMS + VOLUNTEERING_CREDIT_TERMS + SUBMISSION_TERMS + POLICY_DOCUMENT_TERMS)
        allowed.update({"raport", "adeverinta", "evaluare", "recunoastere"})
        return token in allowed

    if original_tokens & set(SCHOLARSHIP_TERMS + CUMULATION_TERMS):
        allowed = set(SCHOLARSHIP_TERMS + CUMULATION_TERMS + POLICY_DOCUMENT_TERMS)
        allowed.update({"conditii", "eligibil", "beneficia", "student", "studenti"})
        return token in allowed

    if original_tokens & {"admitere", "inscriere", "candidat"}:
        return token in {"admitere", "inscriere", "candidat", "dosar", "taxa", "taxe", "program"}

    if original_tokens & {"orar", "orare"}:
        return token in {"orar", "orare", "program"}

    if original_tokens & {"contact", "secretariat"}:
        return token in {"contact", "secretariat", "telefon", "email", "adresa", "program"}

    if original_tokens & {"cazare", "camin", "camine"}:
        return token in {
            "cazare", "camin", "camine", "student", "studenti", "conditii", "eligibil",
            "documente", "acte", "dosar", "orfan", "orfani", "monoparentala", "social",
            "justificativ", "venituri",
        }

    if _is_social_document_question(original_tokens):
        allowed = set(SOCIAL_CONTEXT_TERMS + DOCUMENT_REQUEST_TERMS + SCHOLARSHIP_TERMS + POLICY_DOCUMENT_TERMS)
        allowed.update({"sprijin", "conditii", "eligibil", "student", "studenti"})
        return token in allowed

    if original_tokens & {"regulament", "regulamente", "metodologie", "procedura", "proceduri"}:
        return token in DOMAIN_VOCABULARY

    return False


def _validated_query_analysis_tokens(values, original_tokens: set[str]) -> list[str]:
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

    allowed_intents = set(INTENT_KEYWORDS) | {"general"}
    return {
        normalize(str(value))
        for value in values
        if normalize(str(value)) in allowed_intents
    }


def _validated_corrected_question(value, base: QueryAnalysis) -> str:
    corrected = normalize(str(value or "")).strip()
    if len(corrected) < 3 or len(corrected) > 260:
        return base.corrected_question

    original_tokens = set(base.tokens)
    corrected_tokens = set(tokenize(corrected))
    if corrected_tokens and corrected_tokens & original_tokens:
        return corrected
    return base.corrected_question


def _build_ollama_query_analysis_prompt(question: str, base: QueryAnalysis) -> tuple[str, str]:
    system_prompt = (
        "Esti un modul local de intelegere a intrebarilor pentru un asistent UVT. "
        "Nu raspunde la intrebare si nu alege surse. Returneaza exclusiv JSON valid."
    )
    user_prompt = f"""
Analizeaza intrebarea unui student UVT si returneaza doar acest JSON:
{{
  "corrected_question": "intrebarea corectata scurt, in romana fara diacritice obligatorii",
  "intent": "una dintre: orar, burse, contact, admitere, regulamente, studenti, general",
  "is_policy_question": true,
  "keywords": ["termeni UVT relevanti pentru cautare"],
  "exclude_intents": ["intentii care nu se potrivesc"]
}}

Reguli:
- Nu introduce informatii care nu sunt sustinute de intrebare.
- Keywords trebuie sa fie substantive/termeni scurti utili pentru cautare, nu propozitii.
- Daca apar "credite" si "voluntariat", prefera intent regulamente/studenti, nu admitere.
- Daca "dosar" apare fara context de admitere/candidat/inscriere, nu presupune admitere.
- Pentru reguli, conditii, cumul, metodologii, proceduri, portofolii sau documente, marcheaza is_policy_question true.

Intrebare originala: {question}
Analiza deterministica existenta:
{base.to_dict()}
""".strip()
    return system_prompt, user_prompt


def request_ollama_query_analysis(question: str, base: QueryAnalysis) -> dict | None:
    system_prompt, user_prompt = _build_ollama_query_analysis_prompt(question, base)
    try:
        return ask_ollama_json(
            system_prompt,
            user_prompt,
            timeout_seconds=OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS,
            num_predict=220,
        )
    except Exception:
        return None


def merge_ollama_query_analysis(question: str, base: QueryAnalysis, suggestion: dict | None) -> QueryAnalysis:
    if not isinstance(suggestion, dict):
        return base

    original_tokens = set(base.tokens)
    corrected_question = _validated_corrected_question(suggestion.get("corrected_question"), base)
    tokens = tuple(tokenize(corrected_question)) or base.tokens
    keyword_tokens = _validated_query_analysis_tokens(suggestion.get("keywords"), original_tokens | set(tokens))
    excluded_intents = _validated_query_analysis_intents(suggestion.get("exclude_intents"))

    intent_text = normalize(str(suggestion.get("intent") or ""))
    allowed_intents = set(INTENT_KEYWORDS) | {"general"}
    candidate_tokens = list(dict.fromkeys([*tokens, *keyword_tokens]))
    candidate_text = " ".join([corrected_question, *candidate_tokens])
    scores = _score_intents(candidate_text, candidate_tokens)
    for excluded in excluded_intents:
        if excluded in scores:
            scores[excluded] -= 100

    best_intent = max(scores, key=scores.get)
    intent = best_intent if scores[best_intent] > 0 else base.intent
    if intent_text in allowed_intents and intent_text not in excluded_intents:
        suggested_score = scores.get(intent_text, 0)
        current_score = scores.get(intent, 0)
        if suggested_score >= max(1, current_score - 2):
            intent = intent_text

    suggested_policy = suggestion.get("is_policy_question")
    is_policy_question = bool(
        base.is_policy_question
        or detect_policy_question(candidate_text, intent)
        or (suggested_policy is True and (
            intent == "regulamente"
            or bool({"regulament", "metodologie", "procedura", "conditii", "eligibil", "portofoliu"} & set(candidate_tokens))
        ))
    )
    page_type_preferences = build_page_type_preferences(intent, is_policy_question, tokens)
    expanded_tokens = list(expand_query_tokens(tokens, intent, is_policy_question))
    for token in keyword_tokens:
        if token not in expanded_tokens:
            expanded_tokens.append(token)

    corrections = list(base.corrections)
    if corrected_question != base.corrected_question:
        corrections.append("ollama_query_rewrite")
    if keyword_tokens:
        corrections.append("ollama_keywords")
    if excluded_intents:
        corrections.append("ollama_excluded:" + ",".join(sorted(excluded_intents)))

    return QueryAnalysis(
        original_question=question,
        normalized_question=normalize(question),
        corrected_question=corrected_question,
        tokens=tokens,
        expanded_tokens=tuple(dict.fromkeys(expanded_tokens)),
        intent=intent,
        is_policy_question=is_policy_question,
        page_type_preferences=page_type_preferences,
        corrections=tuple(dict.fromkeys(corrections)),
    )


def analyze_query(question: str) -> QueryAnalysis:
    base = analyze_query_deterministic(question)
    if not query_analysis_enabled():
        return base
    return merge_ollama_query_analysis(question, base, request_ollama_query_analysis(question, base))
