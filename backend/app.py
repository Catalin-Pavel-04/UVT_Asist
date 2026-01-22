from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Any, Tuple

from flask import Flask, request, jsonify
from flask_cors import CORS

from faculties import FACULTIES

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_PATH = os.path.join(APP_DIR, "data", "docs.json")

app = Flask(__name__)
CORS(app)

def load_docs() -> Dict[str, List[Dict[str, Any]]]:
    with open(DOCS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

DOCS = load_docs()

def tokenize(s: str) -> List[str]:
    s = s.lower()
    s = re.sub(r"[^a-z0-9ăâîșț\s]", " ", s, flags=re.IGNORECASE)
    parts = [p for p in s.split() if len(p) > 2]
    return parts

def score_doc(query_tokens: List[str], doc_text: str) -> int:
    text = doc_text.lower()
    score = 0
    for t in query_tokens:
        if t in text:
            score += 1
    return score

def retrieve(faculty_id: str, question: str, top_k: int = 3) -> List[Dict[str, Any]]:
    docs = DOCS.get(faculty_id) or DOCS.get("uvt") or []
    qt = tokenize(question)
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for d in docs:
        s = score_doc(qt, (d.get("title", "") + " " + d.get("text", "")))
        if s > 0:
            scored.append((s, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:top_k]]

def short_answer(question: str, hits: List[Dict[str, Any]]) -> str:
    q = question.lower()
    if not hits:
        return ("Nu am găsit o potrivire clară în indexul local. "
                "Încearcă să reformulezi întrebarea sau selectează facultatea corectă.")

    if any(k in q for k in ["orar", "schedule", "timetable"]):
        return ("Pentru orar, verifică secțiunea dedicată pe site-ul facultății selectate. "
                "Mai jos ai link-urile unde poți găsi informația.")
    if any(k in q for k in ["burs", "scholar"]):
        return ("Pentru burse, consultă secțiunea Studenți/Burse pe site-ul UVT sau al facultății. "
                "Mai jos ai sursele relevante.")
    if any(k in q for k in ["secretariat", "contact", "program"]):
        return ("Pentru program și contacte, consultă pagina de contact/secretariat a facultății. "
                "Mai jos ai sursele relevante.")

    best = hits[0]
    return (f"Am găsit informații relevante în pagina: {best.get('title','')}. "
            "Mai jos ai link-urile sursă.")

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
    sources = [h.get("url") for h in hits if h.get("url")]

    seen = set()
    uniq_sources = []
    for s in sources:
        if s not in seen:
            uniq_sources.append(s)
            seen.add(s)

    return jsonify({"answer": answer, "sources": uniq_sources})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
