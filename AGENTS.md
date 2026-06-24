# AGENTS.md

Repository-specific guidance for future Codex runs on `UVT_Asist`.

## Product Baseline

- `UVT_Asist` is a bachelor thesis project for answering student questions from official West University of Timisoara sources.
- The Chrome extension popup is the only user-facing interface.
- Flask is the backend.
- Ollama is the local generation layer.
- Ollama embeddings are used for semantic retrieval.
- Qdrant is the local vector database.
- Retrieval must stay local-index-first, with live fetch only as a narrow verification step for selected official URLs.

## Repo Structure

- `backend/app.py`: Flask entrypoint, CORS configuration, blueprint registration, and direct `python backend/app.py` startup.
- `backend/api/`: thin HTTP routes for health, faculties, indexing status, chat, and feedback.
- `backend/services/`: application services for chat orchestration, response payloads, source verification, feedback logging, health reporting, indexing state, telemetry, cache, guards, and answer generation.
- `backend/core/`: environment configuration and backend logging setup.
- `backend/rag/`: Romanian normalization, typo correction, query analysis, intent detection, Qdrant retrieval orchestration, deterministic reranking, and confidence scoring.
- `backend/rag/ranking/`: lexical, faculty, page-type, and policy scoring signals.
- `backend/ollama_client.py`: local Ollama chat and embedding API client.
- `backend/vector_store.py`: Qdrant collection setup, payload indexes, vector upsert, filtered search, status reporting.
- `backend/vector_indexer.py`: chunk embedding text formatting and vector index rebuild logic.
- `backend/build_index.py`: crawler plus JSON and Qdrant index builder.
- `backend/page_index.py`: index schema, page classification, chunking, legacy index upgrade/loading.
- `backend/live_fetch.py`: official page fetching and text extraction for HTML, PDF, DOCX, text, and optional OCR assets.
- `backend/site_cache.py`: short-lived live verification cache.
- `backend/prompts.py`: local RAG prompt contract.
- `backend/faculties.py`: UVT and faculty source configuration.
- `backend/scripts/build_vector_index.py`: rebuild Qdrant from existing JSON chunks.
- `backend/scripts/smoke_retrieval.py`: retrieval regression smoke test that expects Qdrant retrieval.
- `extension/manifest.json`: Chrome extension manifest.
- `extension/popup.html`: popup markup.
- `extension/popup.css`: popup visual system.
- `extension/popup.js`: popup state, faculty selection, chat behavior, API integration, source rendering.
- `README.md`: thesis-ready setup, architecture, and validation guide.

## Commands

Setup:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Start local AI services:

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text
ollama serve
docker run --name uvt-asist-qdrant -p 6333:6333 -p 6334:6334 -v ${PWD}\qdrant_storage:/qdrant/storage qdrant/qdrant
```

If Docker is unavailable for development, set `QDRANT_PATH=backend/data/qdrant_local` in `backend/.env` to use Qdrant Client local storage. Prefer the server mode for demos.

Build full crawler plus vector index:

```powershell
python backend\build_index.py
```

Rebuild only vectors from existing JSON chunks:

```powershell
python backend\scripts\build_vector_index.py
```

Run backend and health check:

```powershell
python backend\app.py
Invoke-RestMethod http://127.0.0.1:5000/health
```

Run retrieval validation:

```powershell
python backend\scripts\smoke_retrieval.py
```

## Retrieval Architecture

- `backend/data/page_index.json` remains the readable local chunk snapshot.
- Qdrant is the searchable vector store and should contain one point per chunk.
- Qdrant payloads must include `chunk_id`, `faculty_id`, `page_type`, `title`, `url`, `chunk_text`, and `last_indexed`.
- Query flow:
  1. normalize Romanian text;
  2. correct common student typos;
  3. detect intent;
  4. detect policy/regulation-style questions;
  5. embed the query with Ollama;
  6. search Qdrant with `faculty_id` and `page_type` metadata filters;
  7. rerank candidates with semantic, lexical, URL, title, faculty, page-type, and policy signals;
  8. live-verify only the best source pages;
  9. send only the strongest official evidence to Ollama generation.
- Specific official pages must beat generic UVT/faculty homepages.
- Policy, eligibility, scholarship cumulation, methodology, and regulation questions should strongly prefer regulations or UVT-level methodology pages.

## Coding Conventions

- Keep Flask as the only backend server.
- Keep popup behavior extension-only; do not add a separate web frontend.
- Do not reintroduce remote AI APIs.
- Keep model names configurable through `backend/.env`.
- If the embedding model changes, rebuild Qdrant.
- Use deterministic retrieval/reranking code for source selection. Do not delegate source choice to the LLM.
- Prefer official UVT and faculty URLs. Do not add unofficial sources as evidence.
- Be explicit when retrieval is weak; low confidence is better than hallucinated specificity.
- Preserve source-card cleanliness: popup cards should show only source title and source URL.
- Keep confidence metadata, live verification indicators, recent questions, dark mode, empty/loading/backend-unavailable states working.
- Avoid broad refactors unrelated to the retrieval/backend/UI contract.

## Thesis-Readiness Expectations

- The app must be demoable as Chrome extension + Flask backend + Ollama + Qdrant.
- `/health` should report Ollama models, Qdrant collection status, JSON index status, retrieval mode, and caches.
- Smoke retrieval should use Qdrant, not just the JSON lexical fallback.
- Core demo scenarios:
  - `info`: `Unde gasesc orarul?` should prefer `info.uvt.ro/orare`.
  - `info`: `Unde gasesc secretariatul facultatii de informatica?` should prefer `info.uvt.ro/contact`.
  - `uvt`: `Este posibil ca un student sa beneficieze de 2 burse?` should prefer scholarship methodology/regulation sources.
  - `uvt`: `Unde gasesc informatii despre admitere?` should prefer official admission pages.
  - `info`: `Unde gasesc orrarul la info?` should still route to Informatics schedule.
- Failure states should be presentable: backend unavailable, Ollama unavailable, Qdrant unavailable, weak retrieval, and no useful source found.

## Definition Of Done

A change is done when:

- Remote AI APIs are not used in runtime code.
- Ollama generation and Ollama embeddings remain the configured local AI path.
- Qdrant remains the vector retrieval store.
- Official source URLs remain visible and accurate in responses and popup source cards.
- Weak or missing evidence is surfaced honestly through confidence/fallback behavior.
- Relevant validation has been run:
  - `python backend\scripts\smoke_retrieval.py` after retrieval, vector, ranking, index schema, or crawler changes.
  - `python backend\app.py` plus `/health` after backend/API changes.
  - `python backend\build_index.py` after crawler, source configuration, extraction, chunking, or full index changes.
  - `python backend\scripts\build_vector_index.py` after embedding model or vector-store changes.
  - Manual popup checks after extension or response-payload changes.
- The final response states what changed, what was validated, and any known remaining risk.
