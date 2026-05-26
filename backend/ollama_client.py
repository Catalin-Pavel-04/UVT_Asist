from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_GENERATION_MODEL = "qwen3:4b"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
REQUEST_TIMEOUT_SECONDS = max(15, int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "120")))
EMBED_TIMEOUT_SECONDS = max(15, int(os.getenv("OLLAMA_EMBED_TIMEOUT_SECONDS", "120")))
MAX_EMBED_TEXT_CHARS = max(1000, int(os.getenv("OLLAMA_MAX_EMBED_TEXT_CHARS", "6000")))
QUERY_ANALYSIS_TIMEOUT_SECONDS = max(1, int(os.getenv("OLLAMA_QUERY_ANALYSIS_TIMEOUT_SECONDS", "8")))


@dataclass(frozen=True)
class OllamaSettings:
    base_url: str
    generation_model: str
    embedding_model: str


def get_ollama_settings() -> OllamaSettings:
    return OllamaSettings(
        base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
        or DEFAULT_OLLAMA_BASE_URL,
        generation_model=os.getenv("OLLAMA_GENERATION_MODEL", DEFAULT_GENERATION_MODEL).strip()
        or DEFAULT_GENERATION_MODEL,
        embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
        or DEFAULT_EMBEDDING_MODEL,
    )


def _ollama_url(path: str) -> str:
    settings = get_ollama_settings()
    return f"{settings.base_url}/{path.lstrip('/')}"


def _strip_thinking_blocks(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def ask_ollama(system_prompt: str, user_prompt: str) -> str:
    settings = get_ollama_settings()
    payload = {
        "model": settings.generation_model,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": f"/no_think\n\n{user_prompt.strip()}"},
        ],
        "options": {
            "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.15")),
            "top_p": float(os.getenv("OLLAMA_TOP_P", "0.9")),
            "num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "700")),
        },
    }

    response = requests.post(_ollama_url("/api/chat"), json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    content = ((data.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("Ollama did not return answer text.")
    return _strip_thinking_blocks(content)


def _extract_json_object(text: str) -> dict:
    cleaned = _strip_thinking_blocks(text)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise RuntimeError("Ollama did not return a JSON object.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeError("Ollama JSON response is not an object.")
    return value


def ask_ollama_json(
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: int | None = None,
    num_predict: int = 220,
) -> dict:
    settings = get_ollama_settings()
    payload = {
        "model": settings.generation_model,
        "stream": False,
        "think": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": f"/no_think\n\n{user_prompt.strip()}"},
        ],
        "options": {
            "temperature": 0,
            "top_p": 0.8,
            "num_predict": max(80, int(num_predict)),
        },
    }

    response = requests.post(
        _ollama_url("/api/chat"),
        json=payload,
        timeout=timeout_seconds or QUERY_ANALYSIS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    content = ((data.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("Ollama did not return JSON content.")
    return _extract_json_object(content)


def _normalize_embedding_response(data: dict, expected_count: int) -> list[list[float]]:
    embeddings = data.get("embeddings")
    if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
        return [[float(value) for value in vector] for vector in embeddings]

    embedding = data.get("embedding")
    if isinstance(embedding, list):
        return [[float(value) for value in embedding]]

    if expected_count == 0:
        return []
    raise RuntimeError("Ollama did not return embeddings.")


def _post_embed(payload: dict, expected_count: int) -> list[list[float]]:
    response = requests.post(_ollama_url("/api/embed"), json=payload, timeout=EMBED_TIMEOUT_SECONDS)
    response.raise_for_status()
    return _normalize_embedding_response(response.json(), expected_count)


def _post_legacy_embedding(model: str, text: str) -> list[float]:
    response = requests.post(
        _ollama_url("/api/embeddings"),
        json={"model": model, "prompt": text},
        timeout=EMBED_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    vectors = _normalize_embedding_response(response.json(), 1)
    if not vectors:
        raise RuntimeError("Ollama did not return a legacy embedding.")
    return vectors[0]


def _model_is_installed(model_name: str, installed_models: list[str]) -> bool:
    if model_name in installed_models:
        return True
    if ":" not in model_name:
        return f"{model_name}:latest" in installed_models or any(
            installed.startswith(f"{model_name}:") for installed in installed_models
        )
    return False


def embed_text(text: str) -> list[float]:
    vectors = embed_texts([text])
    if not vectors:
        raise RuntimeError("Ollama did not return an embedding.")
    return vectors[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    cleaned_texts = [str(text).strip()[:MAX_EMBED_TEXT_CHARS] for text in texts]
    if not cleaned_texts:
        return []

    settings = get_ollama_settings()
    input_value = cleaned_texts[0] if len(cleaned_texts) == 1 else cleaned_texts
    payload = {
        "model": settings.embedding_model,
        "input": input_value,
    }

    try:
        vectors = _post_embed(payload, len(cleaned_texts))
        if len(vectors) == len(cleaned_texts):
            return vectors
        if len(cleaned_texts) == 1 and len(vectors) == 1:
            return vectors
    except Exception:
        pass

    vectors: list[list[float]] = []
    for text in cleaned_texts:
        try:
            vectors.extend(_post_embed({"model": settings.embedding_model, "input": text}, 1))
        except Exception:
            vectors.append(_post_legacy_embedding(settings.embedding_model, text))
    return vectors


def get_ollama_status() -> dict:
    settings = get_ollama_settings()
    status = {
        "base_url": settings.base_url,
        "generation_model": settings.generation_model,
        "embedding_model": settings.embedding_model,
        "available": False,
        "models": [],
    }

    try:
        response = requests.get(_ollama_url("/api/tags"), timeout=5)
        response.raise_for_status()
        models = response.json().get("models") or []
        status["models"] = [str(model.get("name", "")) for model in models if model.get("name")]
        status["available"] = True
        status["generation_model_available"] = _model_is_installed(
            settings.generation_model,
            status["models"],
        )
        status["embedding_model_available"] = _model_is_installed(
            settings.embedding_model,
            status["models"],
        )
    except Exception as exc:
        status["error"] = str(exc)
        status["generation_model_available"] = False
        status["embedding_model_available"] = False

    return status
