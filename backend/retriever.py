from __future__ import annotations

import re
import unicodedata
from collections import Counter

INTENT_KEYWORDS = {
    "orar": ["orar", "schedule", "timetable", "curs", "seminar", "lab"],
    "burse": ["bursa", "burse", "scholarship", "scholarships"],
    "contact": ["contact", "secretariat", "program", "telefon", "email"],
    "admitere": ["admitere", "admission", "inscriere", "dosar", "acte"],
    "mobilitati": ["mobilitate", "erasmus", "exchange"],
    "regulamente": ["regulament", "regulamente", "rules"],
    "examene": ["examen", "examene", "session", "sesiune"],
    "licenta": ["licenta", "disertatie", "graduation"],
    "calendar": ["calendar", "semestru", "vacanta", "vacante", "academic"],
    "taxe": ["taxa", "taxe", "fee", "fees", "plata"],
}

CONVERSATIONAL_PATTERNS = [
    "ce faci",
    "ce mai faci",
    "cum esti",
    "cum merge",
    "cine esti",
    "salut",
    "buna",
    "hello",
    "hi",
    "hey",
    "multumesc",
    "mersi",
    "merci",
    "thanks",
    "ms",
]

VAGUE_PATTERNS = [
    "unde gasesc informatiile",
    "unde gasesc informatii",
    "unde gasesc",
    "cum procedez",
    "nu gasesc",
    "am nevoie de informatii",
    "vreau informatii",
    "imi trebuie informatii",
    "ma poti ajuta",
    "am o intrebare",
]

QUESTION_HINTS = {"unde", "cum", "ce", "care", "cand", "cat", "cine"}


def strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize(text: str) -> str:
    lowered = strip_diacritics(text).lower()
    return re.sub(r"\s+", " ", lowered).strip()


def tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", normalize(text))
    return [token for token in cleaned.split() if len(token) > 1]


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


def classify_question(question: str) -> str:
    query = normalize(question)
    tokens = tokenize(question)
    intent, _ = detect_intent(question)

    if intent != "general":
        return "factual"

    if any(pattern in query for pattern in CONVERSATIONAL_PATTERNS) and len(tokens) <= 6:
        return "conversational"

    if any(pattern in query for pattern in VAGUE_PATTERNS):
        return "vague"

    if len(tokens) <= 4 and any(token in QUESTION_HINTS for token in tokens):
        return "vague"

    if len(tokens) <= 2 and tokens:
        return "conversational"

    return "factual"


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


def score_chunk(question: str, chunk: str, page_title: str = "") -> int:
    query_tokens = [token for token in tokenize(question) if len(token) > 2]
    haystack = normalize(f"{page_title} {chunk}")
    title_haystack = normalize(page_title)

    freq = Counter()
    for token in query_tokens:
        if token in haystack:
            freq[token] += 1

    score = sum(freq.values())
    score += sum(1 for token in query_tokens if token in title_haystack) * 2

    intent, _ = detect_intent(question)
    if intent != "general" and intent in haystack:
        score += 3

    return score


def rank_chunks(question: str, pages: list[dict], top_k: int = 5) -> list[dict]:
    scored = []

    for page in pages:
        page_title = page.get("title", "")
        page_url = page.get("url", "")
        page_text = page.get("text", "")

        for chunk in chunk_text(page_text):
            score = score_chunk(question, chunk, page_title=page_title)
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
