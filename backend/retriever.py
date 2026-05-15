from __future__ import annotations

import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import get_close_matches
from pathlib import PurePosixPath
from typing import Iterable
from urllib.parse import urlparse

from page_index import is_generic_page_title
from ollama_client import embed_text
from vector_store import search_chunks

GENERAL_FACULTY_ID = "uvt"

INTENT_KEYWORDS = {
    "orar": ("orar", "orare", "program cursuri", "program seminar"),
    "burse": ("bursa", "burse", "bursier", "bursieri"),
    "contact": ("contact", "secretariat", "telefon", "email", "adresa", "program public"),
    "admitere": ("admitere", "inscriere", "inscrieri", "candidat", "dosar"),
    "regulamente": ("regulament", "regulamente", "metodologie", "metodologii", "procedura", "proceduri"),
    "studenti": (
        "student", "studenti", "cazare", "camin", "camine", "taxa", "taxe", "studentweb",
        "calendar academic", "structura anului", "an universitar", "anul universitar",
        "inceperea anului",
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
    "regulamente": ("regulamente", "regulament", "metodologie", "metodologii", "procedura", "proceduri"),
    "studenti": ("studenti", "studentweb", "cazare", "camine", "camin", "taxe", "calendar", "structura anului"),
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
    "cumula": "cumulare",
    "cumularea": "cumulare",
    "cumuleaza": "cumulare",
    "caminul": "camin",
    "caminului": "camin",
    "caminele": "camine",
    "caminelor": "camine",
}

STOPWORDS = {
    "a", "ai", "al", "ale", "am", "ar", "as", "asta", "ca", "care", "ce", "cea", "cele", "cel",
    "cei", "cum", "cu", "de", "din", "doar", "e", "este", "fi", "fie", "gasesc", "in", "la",
    "mai", "ma", "mi", "o", "pe", "pentru", "pot", "poate", "sa", "sau", "se", "si", "sunt",
    "cand", "spune", "spune-mi", "te", "rog", "despre", "ceva", "imi", "un", "unei", "unui", "unde", "vreau",
}

DOMAIN_VOCABULARY = {
    "admitere", "adresa", "anexa", "beneficia", "bursa", "burse", "candidat", "cazare",
    "contact", "cumulare", "dosar", "email", "facultate", "informatica", "inscriere",
    "informatii", "informatie", "metodologie", "metodologii", "orar", "orare", "procedura",
    "model", "proceduri", "proba", "program", "regulament", "regulamente", "secretariat",
    "student", "studenti", "subiect", "subiecte",
    "an", "calendar", "camin", "camine", "incepe", "inceperea", "parola", "studentweb",
    "structura", "taxa", "taxe", "telefon", "universitar", "uvt", "wifi",
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
)

POLICY_DOCUMENT_TERMS = ("regulament", "metodologie", "procedura", "anexa", "hotarare")
SCHOLARSHIP_TERMS = ("bursa", "burse", "burselor", "bursieri", "sprijin financiar")
CUMULATION_TERMS = ("cumulare", "cumuleaza", "cumula", "art 5", "art. 5")
VECTOR_SEARCH_LIMIT = max(8, int(os.getenv("VECTOR_SEARCH_LIMIT", "18")))
SEMANTIC_SCORE_WEIGHT = float(os.getenv("SEMANTIC_SCORE_WEIGHT", "58"))

_PREPARED_INDEX_CACHE: dict | None = None
_PREPARED_INDEX_SIGNATURE: tuple | None = None


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
        if remove_stopwords and (token in STOPWORDS or len(token) < 2):
            continue
        tokens.append(token)
    return tokens


def correct_query_terms(question: str) -> tuple[str, list[str]]:
    corrected_tokens: list[str] = []
    corrections: list[str] = []

    for token in tokenize(question, remove_stopwords=False):
        replacement = token
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
    if {"burse", "bursa"} & token_set and {"2", "cumulare", "beneficia", "conditii", "eligibil"} & token_set:
        scores["regulamente"] += 8
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
    if any(phrase in question_text for phrase in POLICY_PHRASES):
        return True
    if {"regulament", "regulamente", "metodologie", "procedura", "proceduri"} & tokens:
        return True
    if {"burse", "bursa"} & tokens and {"2", "cumulare", "beneficia", "conditii", "eligibil"} & tokens:
        return True

    return False


def build_page_type_preferences(intent: str, is_policy_question: bool, tokens: Iterable[str]) -> tuple[str, ...]:
    token_set = set(tokens)
    if is_policy_question:
        if {"burse", "bursa"} & token_set:
            return ("regulamente", "burse", "studenti", "general")
        if intent == "admitere":
            return ("regulamente", "admitere", "general")
        return ("regulamente", "studenti", "general", "burse")

    return INTENT_PAGE_TYPES.get(intent, INTENT_PAGE_TYPES["general"])


def expand_query_tokens(tokens: Iterable[str], intent: str, is_policy_question: bool) -> tuple[str, ...]:
    expanded = list(dict.fromkeys(tokens))
    synonyms = {
        "orar": ("orar", "orare"),
        "burse": ("bursa", "burse", "burselor"),
        "contact": ("contact", "secretariat", "telefon", "email", "adresa"),
        "admitere": ("admitere", "inscriere", "candidat", "dosar"),
        "regulamente": ("regulament", "regulamente", "metodologie", "procedura", "anexa"),
        "studenti": ("student", "studenti", "studentweb", "cazare", "camin", "camine", "taxe", "calendar", "structura", "universitar"),
    }

    for token in synonyms.get(intent, ()):
        if token not in expanded:
            expanded.append(token)

    if is_policy_question:
        for token in ("regulament", "metodologie", "procedura", "anexa", "conditii", "eligibil"):
            if token not in expanded:
                expanded.append(token)
        if {"burse", "bursa"} & set(expanded):
            for token in ("bursa", "burse", "burselor", "cumulare", "beneficia"):
                if token not in expanded:
                    expanded.append(token)

    return tuple(expanded)


def analyze_query(question: str) -> QueryAnalysis:
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


def _counter(tokens: Iterable[str]) -> Counter:
    return Counter(tokens)


def _url_path(url: str) -> str:
    return (urlparse(url).path or "/").rstrip("/") or "/"


def _url_slug_tokens(url: str) -> list[str]:
    path = PurePosixPath(_url_path(url))
    return tokenize(" ".join(path.parts))


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


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
    signals: list[str] = []
    score = 0.0
    query_years = {token for token in analysis.tokens if re.fullmatch(r"20\d{2}", token)}
    query_tokens = set(analysis.tokens)
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
        asks_calendar = bool({"calendar", "structura", "universitar", "an", "incepe", "inceperea"} & query_tokens)

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
            score += 18
            signals.append("faculty:uvt")
        elif analysis.is_policy_question and is_policy_document:
            score += 18
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

    scholarship_question = bool({"burse", "bursa", "burselor"} & query_tokens)
    if scholarship_question:
        if _contains_any(topic_head, SCHOLARSHIP_TERMS):
            score += 26
            signals.append("policy:scholarship_topic")
        else:
            score -= 20
            signals.append("policy:topic_missing")

    asks_cumulation = bool({"2", "cumulare"} & query_tokens)
    if asks_cumulation:
        if _contains_any(combined, CUMULATION_TERMS):
            score += 44
            signals.append("policy:cumulation")
        elif scholarship_question:
            score -= 18
            signals.append("policy:cumulation_missing")

    title_norm = chunk["_title_norm"]
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

    if {"burse", "bursa", "burselor"} & set(analysis.expanded_tokens):
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


def build_query_embedding_text(question: str, analysis: QueryAnalysis) -> str:
    return (
        f"Intrebare student: {question}\n"
        f"Intrebare normalizata: {analysis.corrected_question}\n"
        f"Intent: {analysis.intent}\n"
        f"Intrebare de regulament/metodologie: {analysis.is_policy_question}\n"
        f"Termeni importanti: {' '.join(analysis.expanded_tokens)}"
    )


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
    query_vector = embed_text(build_query_embedding_text(question, analysis))
    hit_groups: list[tuple[str, list[dict]]] = []

    for search_pass in _vector_search_passes(analysis, selected_faculty):
        hits = search_chunks(
            query_vector=query_vector,
            faculty_ids=search_pass["faculty_ids"],
            page_types=search_pass["page_types"],
            limit=VECTOR_SEARCH_LIMIT,
        )
        hit_groups.append((search_pass["label"], hits))

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


def rank_vector_index(question: str, index_document: dict, selected_faculty: str, top_k: int = 6) -> dict:
    analysis = analyze_query(question)
    prepared_index = prepare_index(index_document)
    semantic_hits = _retrieve_semantic_candidates(question, analysis, selected_faculty)
    scored = _score_semantic_candidates(
        semantic_hits,
        analysis,
        selected_faculty,
        prepared_index.get("idf", {}),
    )
    lexical_backfill = _score_lexical_backfill_candidates(
        prepared_index.get("chunks", []),
        analysis,
        selected_faculty,
        prepared_index.get("idf", {}),
    )
    scored = _merge_scored_candidates([scored, lexical_backfill])
    chunks = select_diverse_chunks(scored, top_k=top_k)
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
    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    chunks = select_diverse_chunks(scored, top_k=top_k)
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
    scored.sort(key=lambda item: item["retrieval_score"], reverse=True)
    selected = select_diverse_chunks(scored, top_k=top_k)
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
