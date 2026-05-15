# UVT_Asist

UVT_Asist is a bachelor thesis project that answers student questions using official pages from the West University of Timisoara. The product runs as a Chrome extension popup backed by a local Flask API. All AI components run locally: Ollama generates answers, Ollama creates embeddings, and Qdrant stores the vector index.

The system is designed as local-index-first RAG. Official UVT and faculty pages are crawled into chunks, embedded locally, stored in Qdrant with metadata, retrieved semantically with faculty and page-type filters, reranked with deterministic Romanian query heuristics, optionally live-verified, and then passed to a local Ollama generation model.

## Architecture

- `extension/`: Chrome extension popup used by the student.
- `backend/app.py`: Flask API, chat orchestration, response payloads, source verification, feedback logging, health reporting.
- `backend/ollama_client.py`: local Ollama chat and embedding API client.
- `backend/vector_store.py`: Qdrant collection setup, payload indexes, vector upsert, filtered search, index status.
- `backend/vector_indexer.py`: chunk-to-embedding text formatting and vector index rebuild logic.
- `backend/retriever.py`: Romanian normalization, typo correction, intent detection, policy routing, Qdrant search orchestration, deterministic reranking, confidence scoring.
- `backend/page_index.py`: chunk schema, page type detection, JSON index loading, legacy index upgrade.
- `backend/build_index.py`: crawler plus JSON and Qdrant index builder.
- `backend/live_fetch.py`: official page fetching and text extraction for HTML, PDF, DOCX, text, and optional OCR assets.
- `backend/site_cache.py`: short-lived live verification cache.
- `backend/prompts.py`: local RAG prompt contract.
- `backend/faculties.py`: UVT and faculty source configuration.

## Local AI Stack

Required services:

- Ollama on `http://127.0.0.1:11434`
- Qdrant on `http://127.0.0.1:6333`
- Flask backend on `http://127.0.0.1:5000`
- Chrome extension loaded from `extension/`

Default models are configured in `backend/.env`:

```env
OLLAMA_GENERATION_MODEL=qwen3:4b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

You can switch models by changing those two variables and rebuilding the vector index when the embedding model changes.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Install and start Ollama, then pull local models:

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text
ollama serve
```

Start Qdrant with Docker:

```powershell
docker run --name uvt-asist-qdrant -p 6333:6333 -p 6334:6334 -v ${PWD}\qdrant_storage:/qdrant/storage qdrant/qdrant
```

If the container already exists:

```powershell
docker start uvt-asist-qdrant
```

If Docker is not available, Qdrant Client can run a local embedded store for development. Set this in `backend/.env` before building the vector index:

```env
QDRANT_PATH=backend/data/qdrant_local
```

For thesis demos, the Docker/server mode is easier to inspect and reset.

## Build Or Rebuild The Index

Full crawl plus JSON and Qdrant vector index:

```powershell
python backend\build_index.py
```

Useful crawl controls:

```powershell
python backend\build_index.py --max-urls-per-faculty 90 --max-depth 2 --max-links-per-page 35 --fetch-workers 10
```

Rebuild only the Qdrant vector index from the existing JSON chunks:

```powershell
python backend\scripts\build_vector_index.py
```

The JSON snapshot is written to `backend/data/page_index.json`. Qdrant stores the searchable vector collection named by `QDRANT_COLLECTION`, defaulting to `uvt_asist_chunks`.

## Run The Backend

```powershell
python backend\app.py
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

The health payload reports Ollama availability, configured models, JSON index status, Qdrant collection status, live verification cache, and response cache size.

## Optional Local Test Interface

For backend testing without loading the Chrome extension, open `test_interface.html` directly in a browser while Flask is running on `http://127.0.0.1:5000`.

The page is a development-only test harness for `/health`, `/faculties`, `/chat`, and `/feedback`. It shows the answer, confidence metadata, official sources, health JSON, and raw response JSON. The Chrome extension popup remains the only user-facing product interface.

## Load The Chrome Extension

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Choose Load unpacked.
4. Select the `extension/` folder.
5. Keep Ollama, Qdrant, and Flask running while using the popup.

## How RAG Works

1. Normalize Romanian text and common student typos.
2. Detect intent: `orar`, `contact`, `burse`, `admitere`, `regulamente`, `studenti`, or `general`.
3. Detect policy/regulation-style questions.
4. Embed the normalized query with Ollama.
5. Search Qdrant with metadata filters for `faculty_id` and `page_type`.
6. Retrieve semantic candidates from the local vector collection.
7. Rerank candidates with deterministic boosts for exact title, URL, faculty, page type, policy, and lexical signals.
8. Penalize generic homepages when specific official pages exist.
9. Live-verify only the best source URLs.
10. Send only the best official context chunks to the local Ollama generation model.
11. Return a concise answer, confidence metadata, verification state, and clean source cards.

Each stored Qdrant payload contains:

- `chunk_id`
- `faculty_id`
- `page_type`
- `title`
- `url`
- `chunk_text`
- `last_indexed`

## Example Queries

- Faculty `info`: `Unde gasesc orarul?`
- Faculty `info`: `Unde gasesc secretariatul facultatii de informatica?`
- Faculty `uvt`: `Este posibil ca un student sa beneficieze de 2 burse?`
- Faculty `uvt`: `Se pot cumula bursele?`
- Faculty `uvt`: `Unde gasesc informatii despre admitere?`
- Faculty `info`: `Unde gasesc orrarul la info?`

Expected behavior:

- Informatics schedule questions should strongly prefer `https://info.uvt.ro/orare/`.
- Informatics secretariat questions should strongly prefer the Informatics contact page.
- Scholarship cumulation and eligibility questions should strongly prefer UVT regulations or methodology pages.
- Typo-based questions should still route to the correct faculty and page type.
- If evidence is weak, the answer should say that clearly and still show the best official sources found.

## Validation

Run retrieval smoke tests after index, retriever, embedding, or Qdrant changes:

```powershell
python backend\scripts\smoke_retrieval.py
```

Run backend health after backend changes:

```powershell
python backend\app.py
Invoke-RestMethod http://127.0.0.1:5000/health
```

Manual popup checklist:

1. `info` faculty, ask `Unde gasesc orarul?`; top source should be `info.uvt.ro/orare`.
2. `info` faculty, ask `Unde gasesc secretariatul facultatii de informatica?`; top source should be `info.uvt.ro/contact`.
3. `uvt` faculty, ask `Este posibil ca un student sa beneficieze de 2 burse?`; source should be a scholarship methodology/regulation page.
4. Ask `Unde gasesc informatii despre admitere?`; returned sources should be official admission pages.
5. `info` faculty, ask `Unde gasesc orrarul la info?`; the Informatics schedule page should still win.
6. Stop Flask and open the popup; it should show the backend unavailable state.
7. Ask a vague or unsupported question; confidence should be low and sources should remain official.

## Limitations

- The system answers only from pages present in the local JSON/Qdrant index plus the narrow live verification step.
- If official pages change, rebuild the index.
- If the embedding model changes, rebuild the Qdrant vector collection.
- Ollama model quality and speed depend on local hardware.
- Live fetching is intentionally bounded to keep the demo deterministic.
- OCR support is optional and depends on the separate OCR setup.
- The popup is the only user-facing interface; there is no separate web frontend.
