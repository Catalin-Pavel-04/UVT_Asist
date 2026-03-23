from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_FILE = Path(__file__).with_name(".env")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

load_dotenv(ENV_FILE)


def _get_gemini_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            f"Lipseste GEMINI_API_KEY. Configureaza cheia in {ENV_FILE.name} sau in mediul de executie."
        )

    return api_key


def _get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL


def _extract_text(response_data: dict) -> str:
    candidates = response_data.get("candidates") or []

    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text_parts = [part.get("text", "").strip() for part in parts if part.get("text")]
        if text_parts:
            return "\n".join(text_parts).strip()

    prompt_feedback = response_data.get("promptFeedback") or {}
    finish_reasons = [candidate.get("finishReason") for candidate in candidates if candidate.get("finishReason")]
    details = prompt_feedback.get("blockReason") or ", ".join(finish_reasons) or "raspuns gol"
    raise RuntimeError(f"Gemini nu a returnat text: {details}")


def ask_llm(system_prompt: str, user_prompt: str) -> str:
    model = _get_gemini_model()
    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt.strip()}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt.strip()}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
        },
    }

    response = requests.post(
        f"{GEMINI_API_BASE}/{model}:generateContent",
        params={"key": _get_gemini_api_key()},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return _extract_text(response.json())
