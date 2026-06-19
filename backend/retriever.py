from __future__ import annotations

import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import get_close_matches
from pathlib import PurePosixPath
from typing import Iterable
from urllib.parse import urlparse

from page_index import is_generic_page_title
from ollama_client import ask_ollama_json, embed_text
from vector_store import search_chunks

GENERAL_FACULTY_ID = "uvt"

INTENT_KEYWORDS = {
    "orar": ("orar", "orare", "program cursuri", "program seminar"),
    "burse": ("bursa", "burse", "bursier", "bursieri"),
    "contact": ("contact", "secretariat", "telefon", "email", "adresa", "program public"),
    "admitere": ("admitere", "inscriere", "inscrieri", "candidat"),
    "regulamente": (
        "regulament", "regulamente", "metodologie", "metodologii", "procedura", "proceduri",
        "credite voluntariat", "credite de voluntariat", "portofoliu", "portofolii", "voluntariat",
        "acte", "documente", "documente justificative", "dosar social",
    ),
    "studenti": (
        "student", "studenti", "cazare", "camin", "camine", "taxa", "taxe", "studentweb",
        "calendar academic", "structura anului", "an universitar", "anul universitar",
        "inceperea anului", "semestru", "sesiune", "sesiuni", "vacanta", "vacante", "saptamani",
        "credite voluntariat", "credite de voluntariat", "portofoliu", "portofolii",
        "voluntariat", "acte cazare", "dosar cazare",
    ),
}

INTENT_PAGE_TYPES = {
    "orar": ("orar", "studenti", "general"),
    "burse": ("burse", "regulamente", "studenti", "general"),
    "contact": ("contact", "general"),
    "admitere": ("admitere", "regulamente", "general"),
    "regulamente": ("regulamente", "studenti", "burse", "general"),
    "studenti": ("studenti", "general", "contact"),
    "general": ("general", "studenti", "contact", "admitere", "burse", "orar", "regulamente"),
}

PAGE_HINTS = {
    "orar": ("orare", "orar"),
    "burse": ("burse", "bursa", "burselor"),
    "contact": ("contact", "secretariat"),
    "admitere": ("admitere", "inscriere"),
    "regulamente": (
        "regulamente", "regulament", "metodologie", "metodologii", "procedura", "proceduri",
        "voluntariat", "credite-voluntariat", "credite voluntariat", "documente", "acte",
    ),
    "studenti": (
        "studenti", "studentweb", "cazare", "camine", "camin", "taxe", "calendar", "structura anului",
        "semestru", "sesiune", "sesiuni", "vacanta", "vacante", "saptamani",
        "voluntariat", "credite-voluntariat", "credite voluntariat", "portofoliu", "dosar-cazare",
    ),
}

COMMON_REPLACEMENTS = (
    (r"\bfmi\b", "informatica"),
    (r"\bfac(?:ultatea)?(?:\s+de)?\s+info(?:rmatica)?\b", "informatica"),
    (r"\bmatematica\s+si\s+informatica\b", "informatica"),
    (r"\binformatici\b", "informatica"),
    (r"\binformaticii\b", "informatica"),
    (r"\binformatia\b", "informatica"),
    (r"\borr?ar(?:ul|ului)?\b", "orar"),
    (r"\borarelor\b", "orare"),
    (r"\bsecretar(?:uat|ait)\b", "secretariat"),
    (r"\bsecreteriat\b", "secretariat"),
    (r"\bsecretariatul\b", "secretariat"),
    (r"\bcamine(?:le|lor)?\b", "camine"),
    (r"\bcamin(?:ul|ului)?\b", "camin"),
    (r"\badmietere\b", "admitere"),
    (r"\badmiter[ew]\b", "admitere"),
    (r"\bburs[aeiw]\b", "burse"),
    (r"\bburselor\b", "burse"),
    (r"\bbursele\b", "burse"),
    (r"\bcumuleaz[ae]\b", "cumulare"),
    (r"\bcumulat[ae]?\b", "cumulare"),
    (r"\bdoua\b", "2"),
    (r"\bcredit(?:ele|elor|ului)?\b", "credite"),
    (r"\bdepun(?:erea|erii|e)?\b", "depune"),
    (r"\bportofoli(?:ul|ului|ile|ilor)?\b", "portofoliu"),
    (r"\bvoluntariat(?:ul|ului)?\b", "voluntariat"),
)

TOKEN_ALIASES = {
    "facultatii": "facultate",
    "facultatea": "facultate",
    "studentului": "student",
    "studentilor": "studenti",
    "burselor": "burse",
    "bursei": "bursa",
    "metodologiile": "metodologie",
    "metodologia": "metodologie",
    "regulamentul": "regulament",
    "regulamentele": "regulamente",
    "procedurile": "proceduri",
    "admiterea": "admitere",
    "inscrierea": "inscriere",
    "anul": "an",
    "beneficieze": "beneficia",
    "beneficiez": "beneficia",
    "beneficiaza": "beneficia",
    "creditul": "credite",
    "creditelor": "credite",
    "creditele": "credite",
    "cumula": "cumulare",
    "cumularea": "cumulare",
    "cumuleaza": "cumulare",
    "depunerea": "depune",
    "depunerii": "depune",
    "caminul": "camin",
    "caminului": "camin",
    "caminele": "camine",
    "caminelor": "camine",
    "portofoliile": "portofoliu",
    "portofoliilor": "portofoliu",
    "portofoliului": "portofoliu",
    "voluntariatului": "voluntariat",
    "actele": "acte",
    "documentele": "documente",
    "documentelor": "documente",
    "justificative": "justificativ",
    "parintii": "parinti",
    "parintilor": "parinti",
    "parintele": "parinte",
    "orfanii": "orfani",
    "orfanilor": "orfani",
    "monoparentale": "monoparentala",
    "divortati": "divort",
    "divortata": "divort",
    "divortat": "divort",
    "veniturilor": "venituri",
    "venitului": "venituri",
    "sociala": "social",
    "sociale": "social",
    "saptamana": "saptamani",
    "saptamanile": "saptamani",
    "saptamanilor": "saptamani",
    "semestrul": "semestru",
    "semestrului": "semestru",
    "vacanta": "vacante",
    "vacantele": "vacante",
    "vacantelor": "vacante",
}

STOPWORDS = {
    "a", "ai", "al", "ale", "am", "ar", "as", "asta", "ca", "care", "ce", "cea", "cele", "cel",
    "cei", "cum", "cu", "daca", "dar", "de", "din", "doar", "e", "este", "fi", "fie", "gasesc", "in", "la",
    "mai", "ma", "mi", "o", "pe", "pentru", "pot", "poate", "sa", "sau", "se", "si", "sunt",
    "am", "iar", "le", "nu", "cand", "spune", "spune-mi", "te", "rog", "despre", "ceva", "imi", "pt",
    "un", "unei", "unui", "unde", "vreau",
}

DOMAIN_VOCABULARY = {
    "admitere", "adresa", "anexa", "beneficia", "bursa", "burse", "candidat", "cazare",
    "acte", "adeverinta", "certificat", "certificate", "contact", "cumulare", "depune", "depunere",
    "document", "documente", "dosar", "email", "evaluare", "justificativ",
    "facultate", "formular", "informatica", "inscriere", "informatii", "informatie", "metodologie",
    "metodologii", "orar", "orare", "procedura",
    "model", "portofoliu", "portofolii", "proceduri", "proba", "program", "regulament", "regulamente",
    "raport", "recunoastere", "secretariat", "student", "studenti", "subiect", "subiecte", "voluntariat",
    "an", "calendar", "camin", "camine", "cursuri", "incepe", "inceperea", "parola", "saptamani",
    "semestru", "sesiune", "sesiuni", "studentweb", "structura", "taxa", "taxe", "telefon",
    "universitar", "uvt", "vacante", "wifi", "credit", "credite",
    "familie", "financiar", "monoparentala", "orfan", "orfani", "parinte", "parinti", "social",
    "sociale", "sprijin", "venit", "venituri", "divort", "sentinta", "deces", "intretinere",
}

POLICY_PHRASES = (
    "este posibil",
    "se poate",
    "pot beneficia",
    "poate beneficia",
    "beneficia de",
    "beneficieze de",
    "pot primi",
    "reguli",
    "conditii",
    "eligibil",
    "cumulare",
    "cumuleaza",
    "2 burse",
    "ce acte",
    "acte trebuie",
    "acte am nevoie",
    "documente justificative",
)

POLICY_DOCUMENT_TERMS = ("regulament", "metodologie", "procedura", "anexa", "hotarare")
SCHOLARSHIP_TERMS = ("bursa", "burse", "burselor", "bursieri", "sprijin financiar")
CUMULATION_TERMS = ("cumulare", "cumuleaza", "cumula", "art 5", "art. 5")
VOLUNTEERING_TERMS = ("voluntariat", "voluntar", "voluntari", "ong", "portofoliu", "portofolii")
VOLUNTEERING_CREDIT_TERMS = ("credite", "credit", "creditelor", "transferabile")
SUBMISSION_TERMS = ("depune", "depunere", "depunerea", "portofoliu", "portofolii", "formular", "dosar")
DOCUMENT_REQUEST_TERMS = (
    "acte", "document", "documente", "justificativ", "justificative", "certificat",
    "certificate", "adeverinta", "dosar", "formular",
)
SOCIAL_CONTEXT_TERMS = (
    "orfan", "orfani", "monoparentala", "monoparental", "familie", "parinte", "parinti",
    "divort", "deces", "social", "sociale", "venit", "venituri", "financiar", "intretinere",
    "handicap", "dizabilitati", "vulnerabil",
)
STRONG_SOCIAL_CONTEXT_TERMS = (
    "orfan", "orfani", "monoparentala", "monoparental", "familie", "parinte", "parinti",
    "divort", "deces", "social", "sociale", "venit", "venituri", "intretinere",
    "handicap", "dizabilitati", "vulnerabil",
)
HOUSING_TERMS = ("cazare", "camin", "camine")
ACADEMIC_CALENDAR_TERMS = (
    "calendar", "structura", "universitar", "semestru", "sesiune", "sesiuni",
    "vacante", "saptamani",
)
OFF_TOPIC_SOCIAL_POLICY_TERMS = (
    "recunoasterea-perioadelor",
    "recunoastere perioadelor",
    "mobilitate",
    "mobilitati",
    "erasmus",
    "euro-200",
    "calculator",
    "calculatoare",
    "tabere",
    "tabara",
)
VECTOR_SEARCH_LIMIT = max(8, int(os.getenv("VECTOR_SEARCH_LIMIT", "18")))
SEMANTIC_SCORE_WEIGHT = float(os.getenv("SEMANTIC_SCORE_WEIGHT", "58"))
VECTOR_LEXICAL_BACKFILL_ENABLED = os.getenv("VECTOR_LEXICAL_BACKFILL_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS = max(1, int(os.getenv("OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS", "8")))
OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS = max(4, int(os.getenv("OLLAMA_QUERY_ANALYSIS_MAX_KEYWORDS", "12")))

_PREPARED_INDEX_CACHE: dict | None = None
_PREPARED_INDEX_SIGNATURE: tuple | None = None


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


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text).lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[’`']", "'", value)
    value = re.sub(r"\s+", " ", value).strip()

    for pattern, replacement in COMMON_REPLACEMENTS:
        value = re.sub(pattern, replacement, value)

    return re.sub(r"\s+", " ", value).strip()


def _clean_for_tokens(text: str) -> str:
    return re.sub(r"[^a-z0-9\s-]", " ", normalize(text))


def _canonical_token(token: str) -> str:
    return TOKEN_ALIASES.get(token, token)


def tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    tokens = []
    for raw_token in _clean_for_tokens(text).split():
        token = _canonical_token(raw_token.strip("-"))
        if not token:
            continue
        if remove_stopwords and (token in STOPWORDS or (len(token) < 2 and not token.isdigit())):
            continue
        tokens.append(token)
    return tokens


def correct_query_terms(question: str) -> tuple[str, list[str]]:
    corrected_tokens: list[str] = []
    corrections: list[str] = []

    for token in tokenize(question, remove_stopwords=False):
        replacement = token
        if token in STOPWORDS:
            corrected_tokens.append(replacement)
            continue
        if token not in DOMAIN_VOCABULARY and len(token) >= 4 and not token.isdigit():
            matches = get_close_matches(token, DOMAIN_VOCABULARY, n=1, cutoff=0.82)
            if matches:
                replacement = matches[0]

        corrected_tokens.append(replacement)
        if replacement != token:
            corrections.append(f"{token}->{replacement}")

    corrected_text = " ".join(corrected_tokens).strip()
    return corrected_text or normalize(question), corrections


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
    return os.getenv("OLLAMA_QUERY_ANALYSIS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


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


def _counter(tokens: Iterable[str]) -> Counter:
    return Counter(tokens)


def _url_path(url: str) -> str:
    return (urlparse(url).path or "/").rstrip("/") or "/"


def _url_slug_tokens(url: str) -> list[str]:
    path = PurePosixPath(_url_path(url))
    return tokenize(" ".join(path.parts))


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _contains_token(text: str, token: str) -> bool:
    return bool(re.search(rf"\b{re.escape(token)}\b", text))


def _current_academic_year_start() -> int:
    now = datetime.now()
    return now.year if now.month >= 8 else now.year - 1


def _academic_year_starts(text: str) -> set[int]:
    starts: set[int] = set()
    for match in re.finditer(r"\b(20\d{2})\s*[-–—]\s*(?:20)?(\d{2})\b", text):
        starts.add(int(match.group(1)))
    return starts


def _upload_year_from_path(path: str) -> int | None:
    match = re.search(r"/(20\d{2})/(?:0?[1-9]|1[0-2])(?:/|$)", path)
    return int(match.group(1)) if match else None


def _is_document_url(url: str) -> bool:
    return PurePosixPath(urlparse(url).path.lower()).suffix in {".pdf", ".docx", ".txt"}


def _is_homepage(url: str) -> bool:
    return _url_path(url) == "/"


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


def _page_type_score(chunk: dict, analysis: QueryAnalysis) -> tuple[float, list[str]]:
    page_type = str(chunk.get("page_type") or "general")
    signals: list[str] = []

    if page_type in analysis.page_type_preferences:
        position = analysis.page_type_preferences.index(page_type)
        score = max(8, 28 - position * 6)
        signals.append(f"page_type:{page_type}")
        return score, signals

    if page_type == "general":
        return -2, ["page_type:general"]

    return -10, [f"page_type_mismatch:{page_type}"]


def _specific_page_score(chunk: dict, analysis: QueryAnalysis) -> tuple[float, list[str]]:
    title_url = f"{chunk['_title_norm']} {chunk['_url_norm']}"
    path = chunk["_path"].lower()
    page_type = str(chunk.get("page_type") or "general")
    signals: list[str] = []
    score = 0.0
    query_years = {token for token in analysis.tokens if re.fullmatch(r"20\d{2}", token)}
    query_tokens = set(analysis.tokens)
    expanded_tokens = set(analysis.expanded_tokens)
    title_url_specific_matches = {
        token for token in expanded_tokens
        if len(token) >= 4
        and token not in {"student", "studenti", "uvt", "informatii", "informatie"}
        and _contains_token(title_url, token)
    }
    if path.startswith(("/fr/", "/en/")):
        score -= 30
        signals.append("localized_page_penalty")

    if len(title_url_specific_matches) >= 2:
        score += min(64, 18 * len(title_url_specific_matches))
        signals.append(f"title_url_specific:{len(title_url_specific_matches)}")
    elif title_url_specific_matches & query_tokens:
        score += 10
        signals.append("title_url_specific:1")

    is_exam_model_page = _contains_any(title_url, ("model-subiecte", "model subiecte", "subiecte_"))
    if is_exam_model_page and not {"model", "subiect", "subiecte", "proba"} & query_tokens:
        score -= 70
        signals.append("exam_model_penalty")

    if query_years:
        title_academic_years = set(re.findall(r"20\d{2}", title_url))
        if title_academic_years & query_years:
            score += 30
            signals.append("year:title")
        elif re.search(r"20\d{2}[-_/]20\d{2}", title_url):
            score -= 50
            signals.append("year:title_mismatch")

        if any(year in chunk["_text_norm"][:2200] for year in query_years):
            score += 10
            signals.append("year:content")
    else:
        academic_years = _academic_year_starts(f"{title_url} {chunk['_text_norm'][:1600]}")
        if academic_years:
            latest_year = max(academic_years)
            current_year = _current_academic_year_start()
            if latest_year == current_year:
                score += 34
                signals.append("current_academic_year")
            elif latest_year == current_year - 1:
                score += 8
                signals.append("recent_academic_year")
            elif latest_year < current_year - 1:
                score -= min(42, 18 * (current_year - latest_year - 1))
                signals.append("stale_academic_year")

        upload_year = _upload_year_from_path(path)
        if upload_year and analysis.is_policy_question and (chunk["_is_document"] or page_type == "regulamente"):
            current_year = _current_academic_year_start()
            if upload_year >= current_year:
                score += 28
                signals.append("current_upload_year")
            elif upload_year == current_year - 1:
                score += 8
                signals.append("recent_upload_year")
            elif upload_year < current_year - 1:
                score -= min(48, 12 * (current_year - upload_year - 1))
                signals.append("stale_upload_year")

    page_hints = PAGE_HINTS.get(analysis.intent, ())
    if analysis.intent == "studenti":
        query_text = normalize(analysis.corrected_question)
        query_tokens = set(analysis.tokens)
        page_hints = tuple(hint for hint in page_hints if hint in query_tokens or hint in query_text)

    for hint in page_hints:
        if hint in title_url:
            score += 14
            signals.append(f"hint:{hint}")
            break

    if analysis.intent == "orar":
        if path == "/orare":
            score += 44
            signals.append("schedule_exact_path")
        elif path == "/orar":
            score += 34
            signals.append("schedule_exact_path")
        elif "orar" in path or "orare" in path:
            score += 20
            signals.append("schedule_path")
    elif analysis.intent == "contact":
        if path in {"/contact", "/secretariat"}:
            score += 32
            signals.append("contact_exact_path")
        elif "contact" in path or "secretariat" in path:
            score += 18
            signals.append("contact_path")
    elif analysis.intent == "admitere":
        if not query_years and re.search(r"/20\d{2}/\d{2}/\d{2}/", path):
            score -= 52
            signals.append("admission_dated_news_penalty")
        if "procesul-de-admitere" in path:
            score += 36
            signals.append("admission_process_path")
        if "cum-sa-aplici" in path or "preinscriere" in path:
            score += 18
            signals.append("admission_application_path")
        if "admitere.uvt.ro" in title_url and not re.search(r"/20\d{2}/\d{2}/\d{2}/", path):
            score += 12
            signals.append("admission_official_portal")
        if path in {"/admitere", "/admitere-licenta", "/admitere-masterat"}:
            score += 28
            signals.append("admission_path")
        elif "admitere" in path:
            score += 16
            signals.append("admission_related_path")
    elif analysis.intent == "burse":
        if "burse" in path or "bursa" in path:
            score += 22
            signals.append("scholarship_path")
    elif analysis.intent == "studenti":
        query_tokens = set(analysis.tokens)
        asks_housing = bool({"cazare", "camin", "camine"} & query_tokens)
        asks_fees = bool({"taxa", "taxe"} & query_tokens)
        asks_calendar = is_academic_calendar_query(analysis.corrected_question, query_tokens)

        if asks_housing and _contains_any(title_url, ("cazare", "camin", "camine")):
            score += 46
            signals.append("housing_exact")
        elif asks_housing and _contains_any(chunk["_text_norm"][:1800], ("cazare", "camin", "camine")):
            score += 26
            signals.append("housing_content")
        elif asks_housing and asks_fees and "taxe" in title_url:
            score -= 26
            signals.append("housing_missing")

        if asks_fees and "taxe" in title_url:
            score += 14
            signals.append("student_fees")

        calendar_hit = asks_calendar and (
            "structura anului universitar" in title_url
            or "structura anului universitar" in chunk["_text_norm"][:2200]
            or "inceperea anului universitar" in chunk["_text_norm"][:2200]
        )
        if calendar_hit:
            score += 78
            signals.append("academic_calendar")
            if "structura-anului" in title_url or "structura anului" in title_url:
                score += 26
                signals.append("academic_calendar_title")
            if chunk["_is_document"]:
                score += 34
                signals.append("academic_calendar_document")
        elif asks_calendar:
            score -= 55
            signals.append("calendar_missing")

        dated_year = _upload_year_from_path(path)
        if asks_calendar and dated_year:
            current_year = _current_academic_year_start()
            if dated_year < current_year - 1:
                score -= min(80, 16 * (current_year - dated_year - 1))
                signals.append("calendar_dated_news_penalty")

    query_tokens = set(analysis.expanded_tokens)
    if _has_housing_context(query_tokens) and _contains_any(title_url, ("cazare", "camin", "camine")):
        score += 32
        signals.append("housing_title")

    if chunk["_is_document"]:
        score += 6
        signals.append("document")

    if chunk["_is_homepage"] or is_generic_page_title(chunk.get("title", "")):
        score -= 42
        signals.append("generic_penalty")

    return score, signals


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


def compute_confidence(scored_chunks: list[dict], analysis: QueryAnalysis | dict | None = None) -> dict:
    if not scored_chunks:
        return {
            "label": "low",
            "score": 10,
            "reason": "Nu au fost gasite fragmente oficiale suficient de relevante.",
        }

    analysis_dict = analysis.to_dict() if isinstance(analysis, QueryAnalysis) else (analysis or {})
    top = scored_chunks[0]
    best_score = float(top.get("retrieval_score", 0.0))
    second_score = float(scored_chunks[1].get("retrieval_score", 0.0)) if len(scored_chunks) > 1 else 0.0
    unique_pages = len({chunk.get("url") for chunk in scored_chunks[:4] if chunk.get("url")})
    signals = set(top.get("match_signals", []))
    direct_support = any(
        signal.startswith("lexical:")
        or signal in {"all_terms", "phrase", "housing_exact", "housing_content", "academic_calendar"}
        or signal.startswith("hint:")
        or signal.endswith("_path")
        for signal in signals
    )
    lexical_count = 0
    for signal in signals:
        if signal.startswith("lexical:"):
            try:
                lexical_count = max(lexical_count, int(signal.split(":", 1)[1]))
            except ValueError:
                pass

    numeric_score = int(min(100, 28 + best_score * 0.45 + second_score * 0.12 + unique_pages * 4 + len(signals) * 2))

    if not direct_support:
        numeric_score = min(numeric_score, 44)
    elif lexical_count == 0 and not {"housing_exact", "housing_content", "academic_calendar"} & signals:
        numeric_score = min(numeric_score, 58)
    elif lexical_count == 1 and analysis_dict.get("intent") == "general":
        numeric_score = min(numeric_score, 62)

    if "generic_penalty" in signals:
        numeric_score = min(numeric_score, 58)
    if "faculty:other_uvt_scope_penalty" in signals:
        numeric_score = min(numeric_score, 70)
    if "housing_missing" in signals:
        numeric_score = min(numeric_score, 50)
    if "calendar_missing" in signals:
        numeric_score = min(numeric_score, 50)
    if analysis_dict.get("is_policy_question") and not any(signal.startswith("policy:") for signal in signals):
        numeric_score = min(numeric_score, 48)
    if analysis_dict.get("is_policy_question") and "policy:cumulation_missing" in signals:
        numeric_score = min(numeric_score, 72)
    if top.get("page_type") in analysis_dict.get("page_type_preferences", ()):
        numeric_score = min(100, numeric_score + 4)

    if numeric_score >= 78:
        label = "high"
        reason = "Sursele potrivite corespund bine cu intrebarea, facultatea si tipul paginii."
    elif numeric_score >= 52:
        label = "medium"
        reason = "Exista surse oficiale relevante, dar potrivirea are unele limite."
    else:
        label = "low"
        reason = "Au fost gasite doar dovezi partiale sau prea generale."

    return {"label": label, "score": numeric_score, "reason": reason}
