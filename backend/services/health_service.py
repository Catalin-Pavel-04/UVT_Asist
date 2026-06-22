from __future__ import annotations

from core.config import (
    CHAT_CACHE_VERSION,
    LIVE_VERIFY_ENABLED,
    LIVE_VERIFY_LIMIT,
    STARTUP_FETCH_WORKERS,
    STARTUP_MAX_DEPTH,
    STARTUP_MAX_LINKS_PER_PAGE,
    STARTUP_MAX_URLS_PER_FACULTY,
    STARTUP_REBUILD_FULL_SITE,
    STARTUP_REBUILD_INDEX,
    STARTUP_SKIP_VECTOR_INDEX,
    STARTUP_TERMINAL_PROGRESS,
    STARTUP_USE_SITEMAPS,
)
from ollama_client import get_ollama_status
from page_index import get_index_status
from retriever import query_analysis_enabled
from services.chat_service import get_response_cache_size
from services.indexing_service import get_indexing_state
from site_cache import get_cache_status
from vector_store import get_vector_index_status


def build_health_payload() -> dict:
    ollama_status = get_ollama_status()
    index_status = get_index_status()
    vector_status = get_vector_index_status()
    indexing_status = get_indexing_state()
    status_reasons: list[str] = []

    if indexing_status.get("running"):
        status_reasons.append("Startup index rebuild is still running.")
    elif indexing_status.get("error"):
        status_reasons.append(f"Startup index rebuild failed: {indexing_status['error']}")

    if not ollama_status.get("available"):
        status_reasons.append("Ollama is unavailable.")
    else:
        if not ollama_status.get("generation_model_available"):
            status_reasons.append("Configured Ollama generation model is not installed.")
        if not ollama_status.get("embedding_model_available"):
            status_reasons.append("Configured Ollama embedding model is not installed.")
    if not index_status.get("exists") or not index_status.get("chunk_count"):
        status_reasons.append("JSON index is missing or empty.")
    if not vector_status.get("available") or not vector_status.get("points_count"):
        status_reasons.append("Qdrant vector index is unavailable or empty.")
    elif index_status.get("chunk_count") and vector_status.get("points_count") != index_status.get("chunk_count"):
        status_reasons.append("Qdrant point count does not match the JSON index chunk count.")

    status = "ok" if not status_reasons else "degraded"
    vector_ready = bool(
        ollama_status.get("available")
        and ollama_status.get("embedding_model_available")
        and vector_status.get("available")
        and vector_status.get("points_count")
    )
    retrieval_mode = "qdrant-vector-rag" if vector_ready else "local-json-lexical-fallback"

    return {
        "status": status,
        "status_reasons": status_reasons,
        "ready": status == "ok" and not indexing_status.get("running"),
        "checks": {
            "ollama": bool(ollama_status.get("available")),
            "generation_model": bool(ollama_status.get("generation_model_available")),
            "embedding_model": bool(ollama_status.get("embedding_model_available")),
            "json_index": bool(index_status.get("exists") and index_status.get("chunk_count")),
            "qdrant_index": bool(vector_status.get("available") and vector_status.get("points_count")),
            "index_vector_count_match": bool(
                index_status.get("chunk_count")
                and vector_status.get("points_count") == index_status.get("chunk_count")
            ),
        },
        "llm_provider": "ollama",
        "embedding_provider": "ollama",
        "ollama_query_analysis_enabled": query_analysis_enabled(),
        "retrieval_mode": retrieval_mode,
        "live_verification_enabled": bool(LIVE_VERIFY_ENABLED and LIVE_VERIFY_LIMIT > 0),
        "live_verify_limit": LIVE_VERIFY_LIMIT,
        "chat_cache_version": CHAT_CACHE_VERSION,
        "startup_indexing": {
            "enabled": STARTUP_REBUILD_INDEX,
            "full_site": STARTUP_REBUILD_FULL_SITE,
            "use_sitemaps": STARTUP_USE_SITEMAPS,
            "skip_vector_index": STARTUP_SKIP_VECTOR_INDEX,
            "max_urls_per_faculty": STARTUP_MAX_URLS_PER_FACULTY,
            "max_depth": STARTUP_MAX_DEPTH,
            "max_links_per_page": STARTUP_MAX_LINKS_PER_PAGE,
            "fetch_workers": STARTUP_FETCH_WORKERS,
            "terminal_progress": STARTUP_TERMINAL_PROGRESS,
        },
        "indexing": indexing_status,
        "ollama": ollama_status,
        "index": index_status,
        "vector_index": vector_status,
        "verification_cache": get_cache_status(),
        "response_cache_entries": get_response_cache_size(),
    }
