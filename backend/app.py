from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Dict, List
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS

from faculties import FACULTIES
from live_fetch import extract_candidate_links, fetch_page
from llm_client import ask_llm
from prompts import SYSTEM_PROMPT, build_user_prompt
from retriever import (
    build_clarification_question,
    clarification_reason,
    detect_intent,
    normalize,
    rank_chunks,
    tokenize,
)

app = Flask(__name__)
CORS(app)

FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}
SESSION_STATE: Dict[str, Dict[str, Any]] = defaultdict(
    lambda: {"history": [], "pending": None}
)
FEEDBACK_EVENTS: List[Dict[str, Any]] = []
IGNORED_FACULTY_WORDS = {
    "facultatea",
    "universitatea",
    "vest",
    "timisoara",
    "general",
    "stiinte",
    "ale",
    "de",
    "si",
    "din",
}
MANUAL_FACULTY_ALIASES = {
    "uvt": {"uvt", "general"},
    "arte": {"arte", "design"},
    "cbg": {"cbg", "chimie", "biologie", "geografie"},
    "drept": {"drept"},
    "feaa": {"feaa", "economie", "administrare", "afacerilor"},
    "sport": {"sport", "educatie fizica", "educatie", "fizica"},
    "ffm": {"ffm", "fizica", "matematica"},
    "info": {"info", "informatica"},
    "fmt": {"fmt", "muzica", "teatru"},
    "lift": {"lift", "litere", "istorie", "filosofie", "teologie"},
    "fsas": {"fsas", "sociologie", "asistenta sociala", "asistenta"},
    "fpse": {"fpse", "psihologie", "educatiei"},
    "fsgc": {"fsgc", "guvernarii", "comunicarii"},
}


def canonical_host(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def build_faculty_aliases() -> Dict[str, List[str]]:
    aliases: Dict[str, set[str]] = {faculty["id"]: set() for faculty in FACULTIES}
    for faculty in FACULTIES:
        faculty_id = faculty["id"]
        aliases[faculty_id].add(normalize(faculty_id))
        normalized_name = normalize(faculty["name"])
        aliases[faculty_id].add(normalized_name)
        for token in normalized_name.split():
            if len(token) > 2 and token not in IGNORED_FACULTY_WORDS:
                aliases[faculty_id].add(token)
        aliases[faculty_id].update(MANUAL_FACULTY_ALIASES.get(faculty_id, set()))
    return {
        faculty_id: sorted(items, key=len, reverse=True)
        for faculty_id, items in aliases.items()
    }


FACULTY_ALIASES = build_faculty_aliases()


def resolve_faculty_id(text: str) -> str | None:
    query = normalize(text)
    if not query:
        return None

    best_faculty_id = None
    best_score = 0
    for faculty_id, aliases in FACULTY_ALIASES.items():
        score = sum(len(alias) for alias in aliases if alias and alias in query)
        if score > best_score:
            best_score = score
            best_faculty_id = faculty_id

    return best_faculty_id if best_score > 0 else None


def current_url_bonus(current_url: str, target_url: str) -> int:
    current_host = canonical_host(current_url)
    target_host = canonical_host(target_url)
    if not current_host or not target_host or current_host != target_host:
        return 0

    bonus = 3
    current_parts = [part for part in urlparse(current_url).path.split("/") if part]
    target_parts = [part for part in urlparse(target_url).path.split("/") if part]
    if current_parts and target_parts and current_parts[0] == target_parts[0]:
        bonus += 2
    return bonus


def candidate_url_score(question: str, url: str, current_url: str, faculty_id: str) -> int:
    normalized_url = normalize(url)
    score = 0

    for token in tokenize(question):
        if token in normalized_url:
            score += 2

    if faculty_id in FACULTY_MAP:
        faculty_hosts = {canonical_host(base) for base in FACULTY_MAP[faculty_id]["base_urls"]}
        if canonical_host(url) in faculty_hosts:
            score += 1

    score += current_url_bonus(current_url, url)
    return score


def remember_turn(session_id: str, question: str, answer: str, faculty_id: str, intent: str) -> None:
    state = SESSION_STATE[session_id]
    state["history"].append(
        {
            "question": question,
            "answer": answer,
            "faculty_id": faculty_id,
            "intent": intent,
        }
    )
    state["history"] = state["history"][-6:]


def build_source_details(ranked_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_url: Dict[str, Dict[str, Any]] = {}
    for item in ranked_chunks:
        url = item["url"]
        current = best_by_url.get(url)
        if current is None or item["score"] > current["score"]:
            best_by_url[url] = {
                "title": item["title"],
                "url": url,
                "snippet": item["chunk"][:320],
                "score": item["score"],
            }
    return list(best_by_url.values())


def get_candidate_pages(faculty_id: str, question: str, current_url: str = "") -> List[str]:
    selected_faculty = FACULTY_MAP.get(faculty_id, FACULTY_MAP["uvt"])
    candidate_urls: List[str] = []

    allowed_base_groups = [selected_faculty["base_urls"]]
    if faculty_id != "uvt":
        allowed_base_groups.append(FACULTY_MAP["uvt"]["base_urls"])

    if current_url:
        current_host = canonical_host(current_url)
        allowed_hosts = {
            canonical_host(base)
            for base_group in allowed_base_groups
            for base in base_group
        }
        if current_host in allowed_hosts:
            candidate_urls.append(current_url)

    for base_group in allowed_base_groups:
        for base_url in base_group:
            candidate_urls.append(base_url)
            candidate_urls.extend(
                extract_candidate_links(base_url, base_group, max_links=12)
            )

    seen = set()
    unique_urls = []
    for url in candidate_urls:
        if url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)

    unique_urls.sort(
        key=lambda url: candidate_url_score(question, url, current_url, faculty_id),
        reverse=True,
    )
    return unique_urls[:12]


def merge_pending_clarification(
    session_id: str, question: str, faculty_id: str
) -> tuple[str, str]:
    state = SESSION_STATE[session_id]
    pending = state.get("pending")
    resolved_faculty_id = resolve_faculty_id(question) or faculty_id

    if not pending:
        if faculty_id == "uvt":
            resolved_faculty_id = resolve_faculty_id(question) or faculty_id
        return question, resolved_faculty_id

    original_question = pending["question"]
    reason = pending["reason"]
    pending_faculty_id = pending.get("faculty_id") or faculty_id
    resolved_faculty_id = resolve_faculty_id(question) or pending_faculty_id or faculty_id

    if reason == "faculty" and resolved_faculty_id in FACULTY_MAP:
        combined_question = (
            f"{original_question} pentru {FACULTY_MAP[resolved_faculty_id]['name']}"
        )
    else:
        combined_question = f"{original_question} {question}".strip()

    state["pending"] = None
    return combined_question, resolved_faculty_id


def clarification_payload(
    answer: str,
    faculty_name: str,
    intent: str,
    session_id: str,
) -> Dict[str, Any]:
    return {
        "answer": answer,
        "sources": [],
        "source_details": [],
        "clarification_needed": True,
        "intent": intent,
        "matched_faculty": faculty_name,
        "session_id": session_id,
    }


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
    requested_faculty_id = (data.get("faculty_id") or "uvt").strip()
    current_url = (data.get("current_url") or "").strip()
    session_id = (data.get("session_id") or "").strip() or str(uuid.uuid4())

    if requested_faculty_id not in FACULTY_MAP:
        requested_faculty_id = "uvt"

    if not question:
        return jsonify(
            {
                "answer": "Intrebarea este goala.",
                "sources": [],
                "source_details": [],
                "clarification_needed": False,
                "intent": "general",
                "matched_faculty": FACULTY_MAP[requested_faculty_id]["name"],
                "session_id": session_id,
            }
        )

    effective_question, effective_faculty_id = merge_pending_clarification(
        session_id, question, requested_faculty_id
    )
    if effective_faculty_id not in FACULTY_MAP:
        effective_faculty_id = "uvt"

    faculty = FACULTY_MAP[effective_faculty_id]
    intent, confidence = detect_intent(effective_question)
    reason = clarification_reason(
        effective_question, effective_faculty_id, intent, confidence
    )
    if reason:
        clarification = build_clarification_question(
            effective_question, effective_faculty_id, intent
        )
        SESSION_STATE[session_id]["pending"] = {
            "question": effective_question,
            "faculty_id": effective_faculty_id,
            "intent": intent,
            "reason": reason,
        }
        return jsonify(
            clarification_payload(
                clarification,
                faculty["name"],
                intent,
                session_id,
            )
        )

    candidate_urls = get_candidate_pages(
        effective_faculty_id, effective_question, current_url=current_url
    )

    pages = []
    for url in candidate_urls[:6]:
        page = fetch_page(url)
        if page.get("text"):
            pages.append(page)

    if not pages:
        answer = "Nu am putut obtine continut actual de pe paginile oficiale."
        remember_turn(session_id, effective_question, answer, effective_faculty_id, intent)
        return jsonify(
            {
                "answer": answer,
                "sources": candidate_urls[:6],
                "source_details": [],
                "clarification_needed": False,
                "intent": intent,
                "matched_faculty": faculty["name"],
                "session_id": session_id,
            }
        )

    top_chunks = rank_chunks(
        effective_question,
        pages,
        top_k=5,
        current_url=current_url,
    )
    source_details = build_source_details(top_chunks)
    sources = [item["url"] for item in source_details]

    if not top_chunks:
        answer = (
            "Nu am gasit suficiente informatii relevante in paginile oficiale pentru aceasta intrebare."
        )
        remember_turn(session_id, effective_question, answer, effective_faculty_id, intent)
        return jsonify(
            {
                "answer": answer,
                "sources": [page["url"] for page in pages[:5]],
                "source_details": [],
                "clarification_needed": False,
                "intent": intent,
                "matched_faculty": faculty["name"],
                "session_id": session_id,
            }
        )

    prompt = build_user_prompt(effective_question, faculty["name"], top_chunks)

    try:
        llm_answer = ask_llm(SYSTEM_PROMPT, prompt)
    except Exception as exc:
        llm_answer = f"Eroare la interogarea modelului LLM: {exc}"

    remember_turn(session_id, effective_question, llm_answer, effective_faculty_id, intent)
    return jsonify(
        {
            "answer": llm_answer,
            "sources": sources,
            "source_details": source_details,
            "clarification_needed": False,
            "intent": intent,
            "matched_faculty": faculty["name"],
            "session_id": session_id,
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
