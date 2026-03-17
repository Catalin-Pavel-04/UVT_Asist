from __future__ import annotations

import re
import unicodedata
from collections import Counter
from urllib.parse import urlparse

INTENT_KEYWORDS = {
    "orar": ["orar", "schedule", "timetable", "curs", "seminar", "lab"],
    "burse": ["bursa", "burse", "scholarship", "scholarships"],
    "contact": ["contact", "secretariat", "program", "telefon", "email"],
    "admitere": ["admitere", "admission", "inscriere", "dosar", "acte"],
    "mobilitati": ["mobilitate", "erasmus", "exchange"],
    "regulamente": ["regulament", "regulamente", "rules"],
    "examene": ["examen", "examene", "session", "sesiune"],
    "licenta": ["licenta", "disertatie", "graduation"],
}

AMBIGUOUS_PATTERNS = [
    "unde gasesc informatiile",
    "care e programul",
    "nu gasesc formularul",
    "cum procedez",
    "am nevoie de informatii",
    "unde gasesc",
]


def strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize(text: str) -> str:
    lowered = strip_diacritics(text).lower()
    return re.sub(r"\s+", " ", lowered).strip()


def tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", normalize(text))
    return [token for token in cleaned.split() if len(token) > 2]


def detect_intent(question: str) -> tuple[str, float]:
    query = normalize(question)
    scores = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        scores[intent] = sum(1 for keyword in keywords if keyword in query)

    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]
    if best_score == 0:
        return "general", 0.0

    total_score = sum(scores.values())
    confidence = best_score / max(total_score, 1)
    return best_intent, confidence


def clarification_reason(
    question: str,
    selected_faculty: str,
    intent: str,
    confidence: float,
) -> str | None:
    query = normalize(question)
    token_count = len(tokenize(question))

    if any(pattern in query for pattern in AMBIGUOUS_PATTERNS):
        if intent == "general":
            return "intent"
        if confidence < 0.55:
            return "intent"
        if selected_faculty == "uvt" and token_count <= 4:
            return "faculty"

    if intent == "general":
        return "intent"

    if confidence < 0.45:
        return "intent"

    if token_count <= 3 and selected_faculty == "uvt":
        return "faculty"

    return None


def needs_clarification(
    question: str,
    selected_faculty: str,
    intent: str,
    confidence: float,
) -> bool:
    return clarification_reason(question, selected_faculty, intent, confidence) is not None


def build_clarification_question(
    question: str,
    selected_faculty: str,
    intent: str,
) -> str:
    reason = clarification_reason(question, selected_faculty, intent, 1.0 if intent != "general" else 0.0)
    if reason == "intent":
        return "Te referi la orar, burse, admitere, secretariat sau alt tip de informatie?"
    if reason == "faculty":
        return "Pentru ce facultate ai nevoie de aceasta informatie?"
    if intent == "general":
        return "Te referi la orar, burse, admitere, secretariat sau alt tip de informatie?"
    if selected_faculty == "uvt":
        return "Pentru ce facultate ai nevoie de aceasta informatie?"
    return "Poti reformula putin mai specific intrebarea?"


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    content = text.strip()
    if not content:
        return []

    chunks = []
    start = 0
    total_len = len(content)
    while start < total_len:
        end = min(start + chunk_size, total_len)
        chunk = content[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == total_len:
            break
        start = max(end - overlap, 0)
    return chunks


def current_url_bonus(current_url: str, page_url: str) -> int:
    current_host = urlparse(current_url or "").netloc.lower().removeprefix("www.")
    page_host = urlparse(page_url or "").netloc.lower().removeprefix("www.")
    if not current_host or not page_host or current_host != page_host:
        return 0

    bonus = 2
    current_parts = [part for part in urlparse(current_url).path.split("/") if part]
    page_parts = [part for part in urlparse(page_url).path.split("/") if part]
    if current_parts and page_parts and current_parts[0] == page_parts[0]:
        bonus += 1
    return bonus


def score_chunk(question: str, chunk: str, page_title: str = "", page_url: str = "", current_url: str = "") -> int:
    query_tokens = tokenize(question)
    haystack = normalize(f"{page_title} {chunk}")

    freq = Counter()
    for token in query_tokens:
        if token in haystack:
            freq[token] += 1

    score = sum(freq.values())
    score += sum(1 for token in query_tokens if token in normalize(page_title)) * 2

    intent, _ = detect_intent(question)
    if intent != "general" and intent in haystack:
        score += 3

    score += current_url_bonus(current_url, page_url)
    return score


def rank_chunks(
    question: str,
    pages: list[dict],
    top_k: int = 5,
    current_url: str = "",
) -> list[dict]:
    scored = []

    for page in pages:
        page_title = page.get("title", "")
        page_url = page.get("url", "")
        page_text = page.get("text", "")

        for chunk in chunk_text(page_text):
            score = score_chunk(
                question,
                chunk,
                page_title=page_title,
                page_url=page_url,
                current_url=current_url,
            )
            if score > 0:
                scored.append(
                    {
                        "score": score,
                        "title": page_title,
                        "url": page_url,
                        "chunk": chunk,
                    }
                )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]
