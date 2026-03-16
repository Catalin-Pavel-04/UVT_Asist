from __future__ import annotations

import json
import math
import os
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS

from faculties import FACULTIES

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_PATH = os.path.join(APP_DIR, "data", "docs.json")

app = Flask(__name__)
CORS(app)


def load_docs() -> Dict[str, List[Dict[str, Any]]]:
    if not os.path.exists(DOCS_PATH):
        return {}
    with open(DOCS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_text(text: str) -> str:
    text = strip_diacritics(text or "")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    return [token for token in normalize_text(text).split() if len(token) > 2]


SYNONYM_GROUPS: List[List[str]] = [
    ["orar", "orarul", "schedule", "timetable"],
    ["bursa", "burse", "scholarship", "scholarships"],
    ["secretariat", "contact", "program", "programare"],
    ["cazare", "camin", "camine", "caminul", "cazari", "cămin", "căminul"],
]

INTENT_HINTS: List[Tuple[List[str], str, str]] = [
    (
        ["orar", "schedule", "timetable"],
        "Pentru orare, verifică pagina de orar/licență/master a facultății; sursele de mai jos te duc direct acolo.",
        "orar licență informatică",
    ),
    (
        ["bursa", "burse", "scholarship"],
        "Pentru burse, vezi secțiunea Studenți/Burse a facultății sau UVT.",
        "burse sociale UVT",
    ),
    (
        ["secretariat", "contact", "program"],
        "Pentru programul secretariatului, intră în pagina de Contact/Secretariat a facultății.",
        "program secretariat FEAA",
    ),
    (
        ["cazare", "camin", "camine", "caminul", "cămin", "căminul"],
        "Pentru cazare și cămine, vezi secțiunea Cazare/Cămine din site-ul facultății sau UVT.",
        "cazare cămin UVT",
    ),
]

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "orar": ["orar", "schedule", "timetable", "curs", "seminar"],
    "burse": ["bursa", "burse", "scholarship", "scholarships"],
    "contact": ["contact", "secretariat", "program", "telefon", "email"],
    "admitere": ["admitere", "admission", "inscriere", "dosar", "acte"],
    "cazare": ["cazare", "camin", "camine", "caminul"],
    "mobilitati": ["mobilitate", "mobilitati", "erasmus", "exchange"],
    "regulamente": ["regulament", "regulamente", "metodologie", "procedura", "proceduri"],
}

FOLLOW_UP_PREFIXES = (
    "si",
    "dar",
    "iar",
    "also",
    "what about",
    "cum ramane",
    "cum ramane cu",
)

FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}
SESSIONS: Dict[str, List[Dict[str, str]]] = defaultdict(list)
FEEDBACK_EVENTS: List[Dict[str, Any]] = []


def detect_intent(question: str) -> str:
    normalized_question = normalize_text(question)
    scores = {
        intent: sum(1 for keyword in keywords if keyword in normalized_question)
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    best_intent = max(scores, key=scores.get, default="general")
    return best_intent if scores.get(best_intent, 0) > 0 else "general"


def expand_tokens(tokens: Iterable[str]) -> List[str]:
    expanded = set(tokens)
    for group in SYNONYM_GROUPS:
        group_set = set(group)
        if expanded & group_set:
            expanded |= group_set
    return list(expanded)


def build_snippet(text: str, query_tokens: List[str]) -> str:
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    query_norm = [token.lower() for token in query_tokens]
    for sentence in sentences:
        sentence_norm = normalize_text(sentence)
        if any(token in sentence_norm for token in query_norm):
            return sentence.strip()[:320]
    normalized_full = strip_diacritics(text).lower()
    for token in query_norm:
        pos = normalized_full.find(token)
        if pos != -1:
            start = max(0, pos - 80)
            end = min(len(text), pos + 220)
            return text[start:end].strip()
    if sentences:
        return sentences[0].strip()[:260]
    return text[:260]


def extract_host(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def current_url_bonus(current_url: str, doc_url: str) -> float:
    current_host = extract_host(current_url)
    doc_host = extract_host(doc_url)
    if not current_host or not doc_host or current_host != doc_host:
        return 0.0

    bonus = 0.35
    current_path = [part for part in urlparse(current_url).path.split("/") if part]
    doc_path = [part for part in urlparse(doc_url).path.split("/") if part]
    if current_path and doc_path and current_path[0] == doc_path[0]:
        bonus += 0.15
    return bonus


def is_follow_up(question: str) -> bool:
    normalized_question = normalize_text(question)
    tokens = normalized_question.split()
    if not normalized_question:
        return False
    if any(normalized_question.startswith(prefix) for prefix in FOLLOW_UP_PREFIXES):
        return True
    return len(tokens) <= 4 and any(
        token in tokens
        for token in ("orar", "burse", "contact", "secretariat", "admitere", "cazare", "regulamente")
    )


def expand_question_with_context(question: str, history: List[Dict[str, str]]) -> str:
    if not history or not is_follow_up(question):
        return question
    previous_question = (history[-1].get("question") or "").strip()
    if not previous_question:
        return question
    return f"{previous_question} {question}"


def record_session_turn(session_id: str, question: str, answer: str, faculty_id: str, intent: str) -> None:
    SESSIONS[session_id].append(
        {
            "question": question,
            "answer": answer,
            "faculty_id": faculty_id,
            "intent": intent,
        }
    )
    SESSIONS[session_id] = SESSIONS[session_id][-6:]


def merge_hits(*hit_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for hit_list in hit_lists:
        for hit in hit_list:
            url = hit.get("url") or f"__missing__:{id(hit)}"
            current = merged.get(url)
            if current is None or hit.get("score", 0.0) > current.get("score", 0.0):
                merged[url] = dict(hit)
    return list(merged.values())


class FacultyIndex:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs
        corpus_tokens = []
        self.doc_freq = Counter()
        for doc in docs:
            tokens = tokenize((doc.get("title") or "") + " " + (doc.get("text") or ""))
            corpus_tokens.append(tokens)
            self.doc_freq.update(set(tokens))
        self.doc_tokens = corpus_tokens
        self.doc_lengths = [len(tokens) for tokens in corpus_tokens]
        self.avg_doc_len = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0
        self.n_docs = len(self.doc_tokens)

    def search(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        if not self.doc_tokens:
            return []
        query_tokens = expand_tokens(tokenize(query))
        if not query_tokens:
            return []

        scored_docs: List[Tuple[float, Dict[str, Any]]] = []
        k1 = 1.5
        b = 0.75
        query_token_set = set(query_tokens)

        for tokens, doc in zip(self.doc_tokens, self.docs):
            if not tokens or not self.avg_doc_len:
                continue

            tf = Counter(tokens)
            score = 0.0
            doc_len = len(tokens)
            token_set = set(tokens)

            for term in query_tokens:
                freq = tf.get(term)
                if not freq:
                    continue
                df = self.doc_freq.get(term, 0)
                if df == 0:
                    continue
                idf = math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))
                denom = freq + k1 * (1 - b + b * doc_len / self.avg_doc_len)
                score += idf * (freq * (k1 + 1)) / denom

            coverage = len(token_set & query_token_set) / len(query_token_set)
            title_norm = normalize_text(doc.get("title", ""))
            section_norm = normalize_text(doc.get("section", ""))
            title_hit = 1.0 if any(term in title_norm for term in query_tokens) else 0.0
            section_hit = 1.0 if any(term in section_norm for term in query_tokens) else 0.0
            length_penalty = 1.0 + max((doc_len / (self.avg_doc_len or 1)) - 1, 0) * 0.1
            intent_factor = 1.0

            for group in SYNONYM_GROUPS:
                group_set = set(group)
                if query_token_set & group_set:
                    if token_set & group_set:
                        intent_factor *= 1.1
                    else:
                        intent_factor *= 0.3

            score = (
                score + 0.8 * coverage + 0.4 * title_hit + 0.25 * section_hit
            ) * intent_factor / length_penalty
            if score <= 0:
                continue

            enriched = dict(doc)
            enriched["score"] = round(score, 4)
            enriched["snippet"] = build_snippet(doc.get("text", ""), query_tokens)
            scored_docs.append((score, enriched))

        scored_docs.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in scored_docs[:top_k]]


DOCS = load_docs()
INDICES: Dict[str, FacultyIndex] = {}
for faculty in FACULTIES:
    faculty_id = faculty["id"]
    INDICES[faculty_id] = FacultyIndex(DOCS.get(faculty_id) or [])
INDICES["uvt"] = INDICES.get("uvt") or FacultyIndex(DOCS.get("uvt") or [])


def retrieve(faculty_id: str, question: str, top_k: int = 4, current_url: str = "") -> List[Dict[str, Any]]:
    selected_faculty = faculty_id if faculty_id in INDICES else "uvt"
    index = INDICES.get(selected_faculty) or INDICES.get("uvt")
    if not index:
        return []

    primary_hits = index.search(question, top_k=max(top_k * 2, 8))
    fallback_hits: List[Dict[str, Any]] = []
    if selected_faculty != "uvt" and len(primary_hits) < top_k and INDICES.get("uvt"):
        fallback_hits = INDICES["uvt"].search(question, top_k=top_k)

    hits = merge_hits(primary_hits, fallback_hits)
    if not hits:
        return []

    reranked_hits = []
    for hit in hits:
        enriched_hit = dict(hit)
        enriched_hit["score"] = round(
            float(enriched_hit.get("score", 0.0)) + current_url_bonus(current_url, enriched_hit.get("url", "")),
            4,
        )
        reranked_hits.append(enriched_hit)

    reranked_hits.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return reranked_hits[:top_k]


def short_answer(question: str, hits: List[Dict[str, Any]], used_context: bool = False) -> str:
    if not hits:
        return (
            "Nu am găsit o potrivire clară în indexul local. "
            "Încearcă să reformulezi întrebarea sau selectează facultatea corectă."
        )

    question_norm = normalize_text(question)
    matched_intents = [
        (keys, note, example)
        for keys, note, example in INTENT_HINTS
        if any(keyword in question_norm for keyword in keys)
    ]
    intent_notes = [note for _, note, _ in matched_intents]

    best = hits[0]
    doc_tokens = set(tokenize((best.get("title") or "") + " " + (best.get("text") or "")))
    missing_intents = []
    for keys, _, _ in INTENT_HINTS:
        if any(keyword in question_norm for keyword in keys) and not doc_tokens.intersection(set(keys)):
            missing_intents.extend(keys)

    prefix = "Am folosit și contextul conversației curente. " if used_context else ""

    if missing_intents:
        base_msg = (
            "Nu am găsit încă un fragment care să conțină exact termenii căutați "
            f"({', '.join(sorted(set(missing_intents)))})."
        )
        example = matched_intents[0][2] if matched_intents else "ex: adaugă numele facultății și tipul de informație."
        advice = f"Deschide sursele de mai jos sau reformulează mai specific (ex: '{example}')."
        if intent_notes:
            advice = " ".join([advice] + intent_notes)
        return prefix + f"{base_msg} {advice}"

    section = best.get("section")
    snippet = (best.get("snippet") or "").strip()
    lead = best.get("title", "informațiile găsite")
    if section:
        lead = f"{lead} — {section}"

    parts = []
    if snippet:
        parts.append(f"Iată ce pare relevant în {lead}: {snippet}")
    else:
        parts.append(f"Am găsit o pagină relevantă: {lead}. Vezi sursele de mai jos.")

    score = best.get("score", 0.0)
    if score < 0.6:
        parts.append("Nu sunt 100% sigur; verifică rapid link-urile de mai jos sau reformulează mai specific.")
    if intent_notes:
        parts.extend(intent_notes)

    return prefix + " ".join(parts)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/faculties")
def faculties():
    return {"faculties": [{"id": faculty["id"], "name": faculty["name"]} for faculty in FACULTIES]}


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    faculty_id = (data.get("faculty_id") or "uvt").strip()
    current_url = (data.get("current_url") or "").strip()
    session_id = (data.get("session_id") or "").strip() or str(uuid.uuid4())

    if faculty_id not in FACULTY_MAP:
        faculty_id = "uvt"

    intent = detect_intent(question)
    if not question:
        return jsonify(
            {
                "answer": "Întrebarea este goală.",
                "sources": [],
                "source_details": [],
                "session_id": session_id,
                "intent": intent,
                "matched_faculty": FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])["name"],
            }
        )

    history = SESSIONS.get(session_id, [])
    expanded_question = expand_question_with_context(question, history)
    used_context = expanded_question != question

    hits = retrieve(faculty_id, expanded_question, top_k=4, current_url=current_url)
    answer = short_answer(question, hits, used_context=used_context)

    unique_sources: List[str] = []
    source_details: List[Dict[str, Any]] = []
    seen_sources = set()
    for hit in hits:
        url = hit.get("url")
        if not url or url in seen_sources:
            continue
        seen_sources.add(url)
        unique_sources.append(url)
        source_details.append(
            {
                "title": hit.get("title", ""),
                "url": url,
                "snippet": hit.get("snippet", ""),
                "score": hit.get("score", 0.0),
            }
        )

    record_session_turn(session_id, question, answer, faculty_id, intent)

    return jsonify(
        {
            "answer": answer,
            "sources": unique_sources,
            "source_details": source_details,
            "session_id": session_id,
            "intent": intent,
            "matched_faculty": FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])["name"],
        }
    )


@app.post("/feedback")
def feedback():
    data = request.get_json(silent=True) or {}
    FEEDBACK_EVENTS.append(data)
    if len(FEEDBACK_EVENTS) > 200:
        del FEEDBACK_EVENTS[:-200]
    return jsonify({"ok": True, "received": data})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
