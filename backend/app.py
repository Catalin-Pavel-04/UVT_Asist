from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS

from faculties import FACULTIES
from live_fetch import extract_candidate_links, fetch_page
from llm_client import ask_llm
from prompts import SYSTEM_PROMPT, build_user_prompt
from retriever import classify_question, rank_chunks

app = Flask(__name__)
CORS(app)

FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/faculties")
def faculties():
    return {"faculties": [{"id": faculty["id"], "name": faculty["name"]} for faculty in FACULTIES]}


def get_candidate_pages(faculty_id: str) -> list[str]:
    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    base_urls = faculty["base_urls"]

    candidates = []
    for base in base_urls:
        candidates.append(base)
        candidates.extend(extract_candidate_links(base, base_urls, max_links=12))

    seen = set()
    unique = []
    for url in candidates:
        if url not in seen:
            unique.append(url)
            seen.add(url)

    return unique[:12]


def fetch_ranked_chunks(question: str, faculty_id: str) -> list[dict]:
    candidate_urls = get_candidate_pages(faculty_id)
    pages = []

    for url in candidate_urls[:6]:
        page = fetch_page(url)
        if page.get("text"):
            pages.append(page)

    return rank_chunks(question, pages, top_k=5) if pages else []


def build_sources(top_chunks: list[dict]) -> list[dict]:
    sources = []
    seen_urls = set()

    for chunk in top_chunks:
        url = (chunk.get("url") or "").strip()
        if not url or url in seen_urls:
            continue

        title = (chunk.get("title") or "").strip() or "Sursa oficiala"
        sources.append({"title": title, "url": url})
        seen_urls.add(url)

    return sources


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    faculty_id = (data.get("faculty_id") or "uvt").strip()

    if not question:
        return jsonify(
            {
                "answer": "Intrebarea este goala.",
                "sources": [],
                "matched_faculty": FACULTY_MAP["uvt"]["name"],
            }
        )

    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    query_mode = classify_question(question)
    top_chunks = fetch_ranked_chunks(question, faculty_id) if query_mode == "factual" else []
    sources = build_sources(top_chunks)
    prompt = build_user_prompt(question, faculty["name"], top_chunks, query_mode)

    try:
        llm_answer = ask_llm(SYSTEM_PROMPT, prompt)
    except Exception as exc:
        return jsonify(
            {
                "answer": f"Eroare la interogarea modelului Ollama: {str(exc)}",
                "sources": sources,
                "matched_faculty": faculty["name"],
            }
        )

    return jsonify(
        {
            "answer": llm_answer,
            "sources": sources,
            "matched_faculty": faculty["name"],
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
