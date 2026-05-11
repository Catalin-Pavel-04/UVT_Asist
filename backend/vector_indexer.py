from __future__ import annotations

import os
from typing import Callable

from ollama_client import embed_texts, get_ollama_settings
from vector_store import get_vector_settings, index_chunks

DEFAULT_EMBED_BATCH_SIZE = 8


def chunk_embedding_text(chunk: dict) -> str:
    title = str(chunk.get("title") or chunk.get("url") or "")
    url = str(chunk.get("url") or "")
    faculty_id = str(chunk.get("faculty_id") or "uvt")
    page_type = str(chunk.get("page_type") or "general")
    text = str(chunk.get("chunk_text") or "")
    return (
        f"Titlu: {title}\n"
        f"URL: {url}\n"
        f"Facultate: {faculty_id}\n"
        f"Tip pagina: {page_type}\n"
        f"Continut oficial:\n{text}"
    ).strip()


def _batched(items: list[dict], batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def embed_chunks(
    chunks: list[dict],
    batch_size: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    batch_size = batch_size or int(os.getenv("OLLAMA_EMBED_BATCH_SIZE", str(DEFAULT_EMBED_BATCH_SIZE)))
    vectors: list[list[float]] = []

    for batch in _batched(chunks, max(1, batch_size)):
        vectors.extend(embed_texts([chunk_embedding_text(chunk) for chunk in batch]))
        if progress:
            progress(len(vectors), len(chunks))

    return vectors


def rebuild_vector_index(index_document: dict, recreate: bool = True) -> dict:
    raw_chunks = [
        chunk for chunk in index_document.get("chunks", [])
        if isinstance(chunk, dict) and chunk.get("chunk_text") and chunk.get("chunk_id")
    ]
    chunks_by_id: dict[str, dict] = {}
    for chunk in raw_chunks:
        chunks_by_id.setdefault(str(chunk["chunk_id"]), chunk)

    chunks = list(chunks_by_id.values())
    vectors = embed_chunks(chunks)
    indexed_count = index_chunks(chunks, vectors, recreate=recreate)
    vector_settings = get_vector_settings()
    ollama_settings = get_ollama_settings()

    return {
        "collection": vector_settings.collection_name,
        "qdrant_url": vector_settings.url,
        "qdrant_path": vector_settings.path,
        "embedding_model": ollama_settings.embedding_model,
        "chunk_count": len(chunks),
        "indexed_count": indexed_count,
        "vector_size": len(vectors[0]) if vectors else 0,
    }
