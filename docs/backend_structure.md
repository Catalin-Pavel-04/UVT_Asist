# Backend Structure

`backend/app.py` remains the Flask entry point and public API contract. The route
handlers should stay thin: validate request payloads, call retrieval/generation
helpers, and return the existing JSON response shapes.

## Runtime Layers

- `core/config.py`: loads `backend/.env` once and exposes typed settings helpers.
- `core/logging.py`: centralizes backend logger setup.
- `ollama_client.py`: talks to local Ollama for chat JSON and embeddings.
- `vector_store.py`: owns Qdrant client creation, collection setup, payload
  indexes, upsert, and filtered vector search.
- `page_index.py`: owns the local JSON index schema, page classification, and
  chunking.
- `rag/`: owns Romanian normalization, typo correction, intent detection,
  Qdrant retrieval, deterministic reranking, and confidence scoring.
- `live_fetch.py`: fetches official pages during crawling/index building.
- `site_cache.py`: legacy helper for fetched-page cache status; `/chat` no
  longer performs runtime live verification.
- `vector_indexer.py`: converts JSON chunks into embedding text and rebuilds the
  Qdrant vector collection.

## Compatibility Rules

- Keep `python backend/app.py`, `python backend/build_index.py`,
  `python backend/scripts/build_vector_index.py`, and
  `python backend/scripts/smoke_retrieval.py` runnable.
- If logic is moved out of an existing module, keep import-compatible wrappers
  for scripts and tests that still import the old names.
- Do not let Flask routes choose sources through the LLM. Source selection stays
  deterministic in retrieval/reranking code.
- Public endpoints and response JSON contracts are owned by the Chrome extension
  popup and should remain backward compatible.
