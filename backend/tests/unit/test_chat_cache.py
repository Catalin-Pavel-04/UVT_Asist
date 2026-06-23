from __future__ import annotations

from services import chat_cache


def test_build_cache_key_is_stable_for_same_input() -> None:
    history = [
        {"role": "user", "content": "Salut"},
        {"role": "assistant", "content": "Cu ce te pot ajuta?"},
    ]

    first_key = chat_cache.build_cache_key("info", "Unde gasesc orarul?", history, "built-at", 42)
    second_key = chat_cache.build_cache_key("info", "Unde gasesc orarul?", history, "built-at", 42)

    assert first_key == second_key


def test_build_cache_key_changes_when_cache_version_changes() -> None:
    first_key = chat_cache.build_cache_key("uvt", "orar", [], "built-at", 1, chat_cache_version="v1")
    second_key = chat_cache.build_cache_key("uvt", "orar", [], "built-at", 1, chat_cache_version="v2")

    assert first_key != second_key


def test_get_set_cached_response_roundtrips_copy() -> None:
    chat_cache.RESPONSE_CACHE.clear()
    cache_key = "unit-cache-key"
    response = {"answer": "OK", "sources": [{"url": "https://uvt.ro"}]}

    chat_cache.set_cached_response(cache_key, response)
    response["answer"] = "mutated after set"
    cached = chat_cache.get_cached_response(cache_key)

    assert cached == {"answer": "OK", "sources": [{"url": "https://uvt.ro"}]}
    assert cached is not response

    cached["answer"] = "mutated after get"
    assert chat_cache.get_cached_response(cache_key)["answer"] == "OK"
