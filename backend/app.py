from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib.parse import urljoin

from faculties import FACULTIES
from live_fetch import fetch_page, extract_candidate_links
from retriever import rank_chunks
from prompts import SYSTEM_PROMPT, build_user_prompt
from llm_client import ask_llm

app = Flask(__name__)
CORS(app)

FACULTY_MAP = {f["id"]: f for f in FACULTIES}

PRIORITY_PATHS = [
    "/orare/",
    "/orar/",
    "/studenti/",
    "/contact/",
    "/admitere/",
    "/burse/",
    "/secretariat/"
]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/faculties")
def faculties():
    return {"faculties": [{"id": f["id"], "name": f["name"]} for f in FACULTIES]}


def get_candidate_pages(faculty_id: str) -> list[str]:
    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    base_urls = faculty["base_urls"]

    candidates = []

    for base in base_urls:
        candidates.append(base)

        for path in PRIORITY_PATHS:
            candidates.append(urljoin(base, path.lstrip("/")))

        candidates.extend(extract_candidate_links(base, base_urls, max_links=20))

    seen = set()
    unique = []

    for url in candidates:
        if url not in seen:
            unique.append(url)
            seen.add(url)

    return unique[:20]


def unique_sources_from_chunks(chunks: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for c in chunks:
        url = c["url"]
        if url not in seen:
            result.append({
                "title": c["title"],
                "url": c["url"]
            })
            seen.add(url)

    return result


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    faculty_id = (data.get("faculty_id") or "uvt").strip()

    if not question:
        return jsonify({
            "answer": "Întrebarea este goală",
            "sources": [],
            "matched_faculty": FACULTY_MAP["uvt"]["name"]
        })

    faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    candidate_urls = get_candidate_pages(faculty_id)

    pages = []
    for url in candidate_urls[:3]:
        page = fetch_page(url)
        if page.get("text"):
            pages.append(page)

    top_chunks = rank_chunks(question, pages, top_k=3) if pages else []
    prompt = build_user_prompt(question, faculty["name"], top_chunks)

    try:
        llm_answer = ask_llm(SYSTEM_PROMPT, prompt)
    except Exception as e:
        return jsonify({
            "answer": f"Eroare la interogarea modelului Ollama: {str(e)}",
            "sources": unique_sources_from_chunks(top_chunks),
            "matched_faculty": faculty["name"]
        })

    return jsonify({
        "answer": llm_answer,
        "sources": unique_sources_from_chunks(top_chunks),
        "matched_faculty": faculty["name"]
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
