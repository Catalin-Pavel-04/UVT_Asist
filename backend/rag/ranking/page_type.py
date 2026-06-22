from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlparse

from page_index import is_generic_page_title
from rag.constants import ACADEMIC_CALENDAR_TERMS, PAGE_HINTS
from rag.intent_detection import _has_housing_context, is_academic_calendar_query
from rag.query_analysis import QueryAnalysis
from rag.ranking.lexical import _contains_any, _contains_token
from rag.text_normalization import normalize, tokenize

def _url_path(url: str) -> str:
    return (urlparse(url).path or "/").rstrip("/") or "/"


def _url_slug_tokens(url: str) -> list[str]:
    path = PurePosixPath(_url_path(url))
    return tokenize(" ".join(path.parts))


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
