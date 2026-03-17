from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS

from faculties import FACULTIES
from live_fetch import extract_candidate_links, fetch_page
from llm_client import ask_llm
from prompts import SYSTEM_PROMPT, build_user_prompt
from retriever import rank_chunks

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


def build_source_details(top_chunks: list[dict]) -> list[dict]:
    best_by_url = {}
    for chunk in top_chunks:
        current = best_by_url.get(chunk["url"])
        if current is None or chunk["score"] > current["score"]:
            best_by_url[chunk["url"]] = {
                "title": chunk["title"],
                "url": chunk["url"],
                "snippet": chunk["chunk"][:320],
                "score": chunk["score"],
            }
    return list(best_by_url.values())


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    faculty_id = (data.get("faculty_id") or "uvt").strip()

    if not question:
        return jsonify(
            {
                "answer": "Intrebarea este goala",
                "sources": [],
                "source_details": [],
                "matched_faculty": FACULTY_MAP["uvt"]["name"],
            }
        )

    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    candidate_urls = get_candidate_pages(faculty_id)

    pages = []
    for url in candidate_urls[:6]:
        page = fetch_page(url)
        if page.get("text"):
            pages.append(page)

    top_chunks = rank_chunks(question, pages, top_k=5) if pages else []
    source_details = build_source_details(top_chunks)
    sources = list(dict.fromkeys([chunk["url"] for chunk in top_chunks])) if top_chunks else []
    prompt = build_user_prompt(question, faculty["name"], top_chunks)

    try:
        llm_answer = ask_llm(SYSTEM_PROMPT, prompt)
    except Exception as exc:
        return jsonify(
            {
                "answer": f"Eroare la interogarea modelului Ollama: {str(exc)}",
                "sources": sources,
                "source_details": source_details,
                "matched_faculty": faculty["name"],
            }
        )

    return jsonify(
        {
            "answer": llm_answer,
            "sources": sources,
            "source_details": source_details,
            "matched_faculty": faculty["name"],
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
