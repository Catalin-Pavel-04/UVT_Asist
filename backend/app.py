from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter
from typing import Dict, List, Any, Tuple, Iterable
import math

from flask import Flask, request, jsonify
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
    tokens = [t for t in normalize_text(text).split() if len(t) > 2]
    return tokens


SYNONYM_GROUPS: List[List[str]] = [
    ["orar", "orarul", "schedule", "timetable"],
    ["bursa", "burse", "scholarship", "scholarships"],
    ["secretariat", "contact", "program", "programare"],
    ["cazare", "camin", "camine", "caminul", "cazari", "cămin", "căminul"],
]

INTENT_HINTS: List[Tuple[List[str], str, str]] = [
    (["orar", "schedule", "timetable"], "Pentru orare, verifică pagina de orar/licență/master a facultății; sursele de mai jos te duc direct acolo.", "orar licență informatică"),
    (["bursa", "burse", "scholarship"], "Pentru burse, vezi secțiunea Studenți/Burse a facultății sau UVT.", "burse sociale UVT"),
    (["secretariat", "contact", "program"], "Pentru programul secretariatului, intră în pagina de Contact/Secretariat a facultății.", "program secretariat FEAA"),
    (["cazare", "camin", "camine", "caminul", "cămin", "căminul"], "Pentru cazare și cămine, vezi secțiunea Cazare/Cămine din site-ul facultății sau UVT.", "cazare cămin UVT"),
]


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
    query_norm = [t.lower() for t in query_tokens]
    for sent in sentences:
        sent_norm = normalize_text(sent)
        if any(t in sent_norm for t in query_norm):
            return sent.strip()[:320]
    # Fallback: center a window around the first token match in the raw text
    normalized_full = strip_diacritics(text).lower()
    for t in query_norm:
        pos = normalized_full.find(t)
        if pos != -1:
            start = max(0, pos - 80)
            end = min(len(text), pos + 220)
            return text[start:end].strip()
    # Final fallback
    if sentences:
        return sentences[0].strip()[:260]
    return text[:260]


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
        self.doc_lengths = [len(t) for t in corpus_tokens]
        self.avg_doc_len = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0
        self.n_docs = len(self.doc_tokens)

    def search(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        if not self.doc_tokens:
            return []
        q_tokens = expand_tokens(tokenize(query))
        if not q_tokens:
            return []
        scored_docs: List[Tuple[float, Dict[str, Any]]] = []
        k1 = 1.5
        b = 0.75
        qset = set(q_tokens)
        for tokens, doc in zip(self.doc_tokens, self.docs):
            if not tokens or not self.avg_doc_len:
                continue
            tf = Counter(tokens)
            score = 0.0
            doc_len = len(tokens)
            token_set = set(tokens)
            for term in q_tokens:
                freq = tf.get(term)
                if not freq:
                    continue
                df = self.doc_freq.get(term, 0)
                if df == 0:
                    continue
                idf = math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))
                denom = freq + k1 * (1 - b + b * doc_len / self.avg_doc_len)
                score += idf * (freq * (k1 + 1)) / denom
            # Light heuristics: reward coverage and heading matches, penalize overly long docs.
            coverage = len(set(tokens) & qset) / len(qset)
            title_norm = normalize_text(doc.get("title", ""))
            section_norm = normalize_text(doc.get("section", ""))
            title_hit = 1.0 if any(t in title_norm for t in q_tokens) else 0.0
            section_hit = 1.0 if any(t in section_norm for t in q_tokens) else 0.0
            length_penalty = 1.0 + max((doc_len / (self.avg_doc_len or 1)) - 1, 0) * 0.1
            intent_factor = 1.0
            for group in SYNONYM_GROUPS:
                g = set(group)
                if qset & g:
                    if token_set & g:
                        intent_factor *= 1.1
                    else:
                        intent_factor *= 0.3  # penalize docs that miss key intent terms
            score = (score + 0.8 * coverage + 0.4 * title_hit + 0.25 * section_hit) * intent_factor / length_penalty
            if score <= 0:
                continue
            enriched = dict(doc)
            enriched["score"] = round(score, 4)
            enriched["snippet"] = build_snippet(doc.get("text", ""), q_tokens)
            scored_docs.append((score, enriched))
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored_docs[:top_k]]


DOCS = load_docs()
INDICES: Dict[str, FacultyIndex] = {}
for fac in FACULTIES:
    fid = fac["id"]
    fac_docs = DOCS.get(fid) or []
    INDICES[fid] = FacultyIndex(fac_docs)
INDICES["uvt"] = INDICES.get("uvt") or FacultyIndex(DOCS.get("uvt") or [])


def retrieve(faculty_id: str, question: str, top_k: int = 4) -> List[Dict[str, Any]]:
    idx = INDICES.get(faculty_id) or INDICES.get("uvt")
    if not idx:
        return []
    hits = idx.search(question, top_k=top_k)
    if not hits and faculty_id != "uvt" and INDICES.get("uvt"):
        hits = INDICES["uvt"].search(question, top_k=top_k)
    return hits


def short_answer(question: str, hits: List[Dict[str, Any]]) -> str:
    if not hits:
        return ("Nu am găsit o potrivire clară în indexul local. "
                "Încearcă să reformulezi întrebarea sau selectează facultatea corectă.")

    q_norm = normalize_text(question)
    matched_intents = [(keys, note, example) for keys, note, example in INTENT_HINTS if any(k in q_norm for k in keys)]
    intent_notes = [note for _, note, _ in matched_intents]

    best = hits[0]
    doc_tokens = set(tokenize((best.get("title") or "") + " " + (best.get("text") or "")))
    missing_intents = []
    for keys, _, _ in INTENT_HINTS:
        if any(k in q_norm for k in keys):
            if not doc_tokens.intersection(set(keys)):
                missing_intents.extend(keys)

    if missing_intents:
        base_msg = ("Nu am găsit încă un fragment care să conțină exact termenii căutați "
                    f"({', '.join(sorted(set(missing_intents)))}).")
        example = matched_intents[0][2] if matched_intents else "ex: adaugă numele facultății și tipul de informație."
        advice = f"Deschide sursele de mai jos sau reformulează mai specific (ex: '{example}')."
        if intent_notes:
            advice = " ".join([advice] + intent_notes)
        return f"{base_msg} {advice}"

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

    return " ".join(parts)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/faculties")
def faculties():
    return {"faculties": [{"id": f["id"], "name": f["name"]} for f in FACULTIES]}

@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    faculty_id = (data.get("faculty_id") or "uvt").strip()

    if not question:
        return jsonify({"answer": "Întrebarea este goală.", "sources": []})

    hits = retrieve(faculty_id, question, top_k=4)
    answer = short_answer(question, hits)
    uniq_sources: List[str] = []
    source_details: List[Dict[str, Any]] = []
    seen_sources = set()
    for h in hits:
        url = h.get("url")
        if not url or url in seen_sources:
            continue
        seen_sources.add(url)
        uniq_sources.append(url)
        source_details.append({
            "title": h.get("title", ""),
            "url": url,
            "snippet": h.get("snippet", ""),
            "score": h.get("score", 0.0),
        })

    return jsonify({"answer": answer, "sources": uniq_sources, "source_details": source_details})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
