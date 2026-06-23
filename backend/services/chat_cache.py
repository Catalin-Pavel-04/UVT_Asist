from __future__ import annotations

import copy
import json
import threading
import time

from core.config import CHAT_CACHE_VERSION, RESPONSE_CACHE_TTL
from services.chat_request_parser import normalize_match_text

RESPONSE_CACHE_LOCK = threading.Lock()
RESPONSE_CACHE: dict[str, dict] = {}


def get_response_cache_size() -> int:
    now = time.time()
    with RESPONSE_CACHE_LOCK:
        return sum(1 for item in RESPONSE_CACHE.values() if now - item["timestamp"] < RESPONSE_CACHE_TTL)


def build_cache_key(
    faculty_id: str,
    effective_question: str,
    history: list[dict],
    index_built_at: str | None,
    vector_points_count: int | None,
    chat_cache_version: str = CHAT_CACHE_VERSION,
) -> str:
    payload = {
        "faculty_id": faculty_id,
        "question": normalize_match_text(effective_question),
        "history": history[-2:],
        "index_built_at": index_built_at,
        "vector_points_count": vector_points_count,
        "chat_cache_version": chat_cache_version,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def get_cached_response(cache_key: str) -> dict | None:
    now = time.time()
    with RESPONSE_CACHE_LOCK:
        cached = RESPONSE_CACHE.get(cache_key)
        if cached and now - cached["timestamp"] < RESPONSE_CACHE_TTL:
            return copy.deepcopy(cached["response"])
    return None


def set_cached_response(cache_key: str, response_payload: dict) -> None:
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = {"timestamp": time.time(), "response": copy.deepcopy(response_payload)}
