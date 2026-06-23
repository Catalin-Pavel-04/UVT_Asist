from __future__ import annotations

from core.config import env_int
from ollama_client import ask_ollama_json
from prompts import SYSTEM_PROMPT, build_answer_json_prompt, build_repair_prompt
from services.chat_request_parser import compact_text
from services.response_builder import build_local_fallback_answer

BAD_GENERATION_MARKERS = (
    "okay,",
    "let me",
    "the student is asking",
    "retrieved context",
    "source 1",
    "first, i",
    "i check",
    "i'll check",
)


def answer_needs_fallback(answer: str) -> bool:
    head = " ".join(str(answer).split()).lower()[:900]
    if not head:
        return True
    return any(marker in head for marker in BAD_GENERATION_MARKERS)


def ask_ollama_answer(answer_prompt: str, ask_ollama_json_func=ask_ollama_json) -> str:
    response = ask_ollama_json_func(
        SYSTEM_PROMPT,
        build_answer_json_prompt(answer_prompt),
        timeout_seconds=env_int("OLLAMA_REQUEST_TIMEOUT_SECONDS", "120", minimum=15),
        num_predict=env_int("OLLAMA_NUM_PREDICT", "700", minimum=350),
    )
    answer = str(response.get("answer") or "").strip()
    if not answer:
        raise RuntimeError("Ollama did not return an answer field.")
    return answer


def repair_generated_answer(prompt: str, flawed_answer: str, ask_ollama_json_func=ask_ollama_json) -> str | None:
    repaired_answer = ask_ollama_answer(
        build_repair_prompt(prompt, flawed_answer),
        ask_ollama_json_func=ask_ollama_json_func,
    )
    if answer_needs_fallback(repaired_answer):
        return None
    return repaired_answer


def generate_answer_with_fallback(
    prompt: str,
    retrieval_result: dict,
    ask_ollama_json_func=ask_ollama_json,
) -> tuple[str, dict]:
    generation = {"mode": "ollama"}
    try:
        answer = ask_ollama_answer(prompt, ask_ollama_json_func=ask_ollama_json_func)
        if answer_needs_fallback(answer):
            repaired_answer = repair_generated_answer(
                prompt,
                answer,
                ask_ollama_json_func=ask_ollama_json_func,
            )
            if repaired_answer:
                generation = {"mode": "ollama_repair"}
                answer = repaired_answer
            else:
                generation = {"mode": "fallback_bad_generation"}
                answer = build_local_fallback_answer(
                    retrieval_result,
                    reason="Raspunsul generat de Ollama nu a respectat contractul de siguranta.",
                )
    except Exception as exc:
        generation = {"mode": "fallback_ollama_error", "error": compact_text(exc, 800)}
        answer = build_local_fallback_answer(
            retrieval_result,
            reason="Ollama nu a putut genera raspunsul in acest moment.",
        )

    return answer, generation
