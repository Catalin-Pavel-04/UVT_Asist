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
- `backend/evaluation/eval_questions.json`: versioned RAG evaluation questions.
- `backend/scripts/evaluate_rag.py`: local evaluation runner that writes JSON, CSV, and Markdown reports.
- `backend/scripts/demo_check.py`: reproducible local demo readiness checker.

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
OLLAMA_QUERY_ANALYSIS_ENABLED=false
```

You can switch models by changing those two variables and rebuilding the vector index when the embedding model changes.
When `OLLAMA_QUERY_ANALYSIS_ENABLED=true`, the backend first asks Ollama for a short JSON query rewrite, intent, and keyword hints. Those hints are sanitized against the UVT vocabulary and only influence retrieval; deterministic Qdrant search and reranking still choose the final sources.

## Demo rapid

Run all commands from the repository root.

1. Create and activate the Python environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

2. Start Ollama in one terminal, then pull the local models from another terminal:

```powershell
ollama serve
```

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

3. Start Qdrant with Docker Compose:

```powershell
docker compose up -d qdrant
```

Qdrant uses the pinned image from `docker-compose.yml` for thesis demo reproducibility. If the Qdrant version is changed later, rebuild the vector index before presenting.

4. Build the JSON and Qdrant indexes:

```powershell
python backend\build_index.py
```

5. Start Flask and check health:

```powershell
python backend\app.py
Invoke-RestMethod http://127.0.0.1:5000/health
```

6. Load the Chrome extension:

- Open `chrome://extensions`.
- Enable Developer mode.
- Choose Load unpacked.
- Select the `extension/` folder.

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

Start Qdrant with Docker Compose. The Compose file pins the Qdrant image for reproducible demos:

```powershell
docker compose up -d qdrant
```

If the container already exists:

```powershell
docker compose up -d qdrant
```

If Docker is not available, Qdrant Client can run a local embedded store for development. Set this in `backend/.env` before building the vector index:

```env
QDRANT_PATH=backend/data/qdrant_local
```

For thesis demos, the Docker/server mode is easier to inspect and reset.
Keep the pinned Qdrant version from `docker-compose.yml` for demos. If you change it, run `python backend\scripts\build_vector_index.py` or rebuild the full index before relying on retrieval results.

## Run The Application

Run all commands from the repository root. The app needs three local services running at the same time: Ollama, Qdrant, and the Flask backend. The Chrome extension is then loaded from the `extension/` folder.

Windows wrapper commands are available in `scripts/`:

```powershell
.\scripts\setup.ps1
.\scripts\start_qdrant.ps1
.\scripts\build_index.ps1
.\scripts\build_index.ps1 -VectorOnly
.\scripts\run_backend.ps1
.\scripts\smoke.ps1
.\scripts\test.ps1
.\scripts\test.ps1 -EvaluateRag
```

If `make` is available, the equivalent targets are:

```powershell
make setup
make qdrant
make build-index
make build-vector-index
make backend
make smoke
make test
make eval
make demo-check
```

First run after setup:

1. Start Ollama in a terminal:

```powershell
ollama serve
```

2. Start Qdrant in another terminal:

```powershell
docker compose up -d qdrant
```

Docker Compose creates the container on the first run and reuses it on later runs.

3. Build the local JSON and Qdrant index once:

```powershell
.venv\Scripts\activate
python backend\build_index.py
```

4. Start the Flask backend:

```powershell
python backend\app.py
```

5. Check that the backend is ready:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

6. Load the Chrome extension:

- Open `chrome://extensions`.
- Enable Developer mode.
- Choose Load unpacked.
- Select the `extension/` folder.
- Open the extension popup and ask a question.

For later runs, the usual sequence is shorter: start Ollama, start Qdrant, activate `.venv`, run `python backend\app.py`, then use the already-loaded Chrome extension. Rebuild the index only when official sources, crawler settings, chunking, or the embedding model change.

## Verificare demo

Before a thesis demo, run:

```powershell
python backend\scripts\demo_check.py
```

The script checks Python imports, `backend/.env`, Ollama availability, configured Ollama models, Qdrant, the Flask `/health` endpoint when it is running, the JSON index, and the Qdrant collection status. It prints `OK`, `WARNING`, and `ERROR` lines with concrete recovery commands such as:

- `ollama pull qwen3:4b`
- `ollama pull nomic-embed-text`
- `docker compose up -d qdrant`
- `python backend/build_index.py`
- `python backend/app.py`

## Checklist demo

Use [docs/demo_checklist.md](docs/demo_checklist.md) before the thesis presentation. It lists the local services to start, the questions to demonstrate, and the UI evidence to show to the committee.

## Documentatie tehnica

- [Arhitectura tehnica](docs/architecture.md): descrie extensia Chrome, backendul Flask, crawlerul, chunking-ul, embeddings locale, Qdrant, retrieval, reranking, live verification, generarea cu Ollama si confidence score.
- [Ghid de dezvoltare locala](docs/development.md): setup Windows PowerShell, Ollama, Qdrant, build index, backend Flask si incarcarea extensiei Chrome.
- [Metodologie evaluare RAG/Q&A](docs/evaluation/methodology.md): explica seturile de evaluare, pass/fail, scorul Q&A, Top-1/Top-3 URL, latenta si tratarea intrebarilor fara raspuns sigur.
- [Plan ablation study](docs/evaluation/ablation_plan.md): descrie variantele lexical only, vector only, vector + reranking, live verification si full system.
- [Cazuri de esec si refuz controlat](docs/evaluation/failure_cases.md): exemple de intrebari vagi, personale sau predictive unde sistemul trebuie sa ceara clarificari ori sa refuze un raspuns sigur.
- [Note despre latenta](docs/evaluation/latency_notes.md): surse de latenta, interpretarea medie/mediana si practici pentru reducerea timpului de raspuns.

## Build Or Rebuild The Index

Full crawl plus JSON and Qdrant vector index:

```powershell
python backend\build_index.py
```

Useful crawl controls:

```powershell
python backend\build_index.py --max-urls-per-faculty 90 --max-depth 2 --max-links-per-page 35 --fetch-workers 10
```

Broad crawl using official sitemaps plus deeper link discovery:

```powershell
python backend\build_index.py --full-site
```

With `--full-site`, the default per-faculty URL cap is removed. You can still set a cap explicitly:

```powershell
python backend\build_index.py --full-site --max-urls-per-faculty 500
```

If you prefer the backend to rebuild the complete index at startup, set this in `backend\.env`:

```env
STARTUP_REBUILD_INDEX=true
STARTUP_REBUILD_FULL_SITE=true
STARTUP_USE_SITEMAPS=true
STARTUP_SKIP_VECTOR_INDEX=false
STARTUP_MAX_URLS_PER_FACULTY=0
STARTUP_MAX_DEPTH=5
STARTUP_MAX_LINKS_PER_PAGE=150
STARTUP_FETCH_WORKERS=12
STARTUP_TERMINAL_PROGRESS=true
INDEX_MAX_PAGE_TEXT_CHARS=24000
INDEX_MAX_CHUNKS_PER_PAGE=32
INDEX_MAX_CHUNK_WORD_CHARS=1000
```

Then `python backend\app.py` starts Flask and rebuilds the index in the background. During this period the terminal shows an `Indexare UVT` progress bar, `/chat` returns a temporary indexing response instead of answering from a partial index, while `/health` and `/indexing/status` expose progress for the Chrome popup loading bar. Ollama and Qdrant must be available before backend startup.
The `INDEX_MAX_*` limits keep malformed or extremely large pages from exhausting memory during chunking.
For large full-site indexes, keep `VECTOR_LEXICAL_BACKFILL_ENABLED=false` so runtime questions use Qdrant-first retrieval instead of scanning the full JSON index.

For an offline-runtime demo where answers should come only from the local JSON/Qdrant snapshot, rebuild with the broad crawl, then set this in `backend\.env`:

```env
LIVE_VERIFY_ENABLED=false
LIVE_VERIFY_LIMIT=0
```

This keeps `/chat` from fetching UVT pages at question time. The tradeoff is freshness: rebuild the index whenever official pages change.

Rebuild only the Qdrant vector index from the existing JSON chunks:

```powershell
python backend\scripts\build_vector_index.py
```

The JSON snapshot is written to `backend/data/page_index.json`, with lightweight runtime metadata in `backend/data/page_index.meta.json`. Qdrant stores the searchable vector collection named by `QDRANT_COLLECTION`, defaulting to `uvt_asist_chunks`.

## Run The Backend

```powershell
python backend\app.py
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

The health payload reports Ollama availability, configured models, JSON index status, Qdrant collection status, startup indexing progress, live verification cache, and response cache size.
It also exposes a `ready` flag and component checks for the configured Ollama generation model, embedding model, JSON index, Qdrant index, and JSON/Qdrant chunk-count match.

## Optional Local Test Interface

For backend testing without loading the Chrome extension, open `test_interface.html` directly in a browser while Flask is running on `http://127.0.0.1:5000`.

The page is a development-only test harness for `/health`, `/faculties`, `/chat`, and `/feedback`. It shows the answer, confidence metadata, official sources, health JSON, and raw response JSON. The Chrome extension popup remains the only user-facing product interface.

## Load The Chrome Extension

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Choose Load unpacked.
4. Select the `extension/` folder.
5. Keep Ollama, Qdrant, and Flask running while using the popup.

The popup backend URL can be configured from the extension options page; it remains restricted to local values such as `http://127.0.0.1:5000` or `http://localhost:5000`.

## How RAG Works

1. Normalize Romanian text and common student typos.
2. Optionally ask Ollama for a JSON-only query rewrite and keyword expansion, then validate every term locally.
3. Detect intent: `orar`, `contact`, `burse`, `admitere`, `regulamente`, `studenti`, or `general`.
4. Detect policy/regulation-style questions.
5. Embed the normalized query with Ollama.
6. Search Qdrant with metadata filters for `faculty_id` and `page_type`.
7. Retrieve semantic candidates from the local vector collection.
8. Rerank candidates with deterministic boosts for exact title, URL, faculty, page type, policy, and lexical signals.
9. Penalize generic homepages when specific official pages exist.
10. Live-verify only the best source URLs, unless `LIVE_VERIFY_ENABLED=false`.
11. Use deterministic answers for high-confidence navigation and administrative source questions.
12. Send only the best official context chunks to the local Ollama generation model when synthesis is actually needed.
13. Return a concise answer, confidence metadata, evidence metadata, verification state, and clean source cards.

Each stored Qdrant payload contains:

- `chunk_id`
- `faculty_id`
- `page_type`
- `title`
- `url`
- `chunk_text`
- `last_indexed`

## Evaluare RAG

The repository includes a minimal, measurable RAG evaluation framework for thesis validation. The versioned question set lives in:

```text
backend/evaluation/eval_questions.json
```

It contains Romanian questions grouped by schedule, contact/secretariat, admission, scholarships, regulations/methodologies, housing, academic calendar, volunteering credits, vague questions, and questions without a safe answer in official sources.

Run the evaluation only when Flask, Ollama, and Qdrant are available:

```powershell
python backend\scripts\evaluate_rag.py
```

Useful filters:

```powershell
python backend\scripts\evaluate_rag.py --category burse --limit 5
python backend\scripts\evaluate_rag.py --backend-url http://127.0.0.1:5000 --timeout 180
```

Generated reports are written under `backend/data/evaluation/`:

- `eval_results_<timestamp>.json`: full payloads, sources, evidence, errors, and per-question timings.
- `eval_results_<timestamp>.csv`: compact tabular results for spreadsheet analysis.
- `eval_summary_<timestamp>.md`: human-readable summary with misses and errors.

`backend/data/evaluation/` is ignored by Git because it contains generated local reports. The stable evaluation dataset in `backend/evaluation/eval_questions.json` is versioned.

For thesis write-up guidance, see [docs/evaluation/methodology.md](docs/evaluation/methodology.md), [docs/evaluation/ablation_plan.md](docs/evaluation/ablation_plan.md), and [docs/evaluation/README.md](docs/evaluation/README.md).

Metric meaning:

- `top1_url_match`: the first returned source URL contains one expected official URL fragment.
- `top3_url_match`: at least one of the first three source URLs contains an expected official URL fragment.
- `low_confidence_count`: number of responses marked `confidence=low` or with a very low confidence score.
- `expected_unanswerable_handled_count`: number of questions marked `should_have_answer=false` where the system returned low confidence, no answerable evidence, or no sources.
- `latency`: request time per `/chat` call, reported as average and median seconds.

## Strategii de reducere a halucinațiilor

- Answers are grounded in official UVT and faculty sources from the local JSON/Qdrant index.
- Source selection is performed by Qdrant retrieval plus deterministic reranking; the LLM does not choose the final evidence.
- The backend returns `confidence`, `confidence_score`, and an evidence profile with source counts and top source metadata.
- Live verification is limited to selected top official URLs and can be disabled for offline demos.
- The prompt contract forbids inventing dates, rules, eligibility criteria, or administrative decisions not present in the retrieved context.
- When evidence is weak, the system should state that the official sources are insufficient instead of producing unsupported specificity.

## Example Queries

- Faculty `info`: `Unde găsesc orarul?`
- Faculty `info`: `Unde găsesc secretariatul Facultății de Informatică?`
- Faculty `uvt`: `Este posibil ca un student să beneficieze de 2 burse?`
- Faculty `uvt`: `Se pot cumula bursele?`
- Faculty `uvt`: `Cum se depune dosarul pentru creditele de voluntariat?`
- Faculty `uvt`: `Unde găsesc informații despre admitere?`
- Faculty `info`: `Unde găsesc orrarul la info?`

Expected behavior:

- Informatics schedule questions should strongly prefer `https://info.uvt.ro/orare/`.
- Informatics secretariat questions should strongly prefer the Informatics contact page.
- Scholarship cumulation and eligibility questions should strongly prefer UVT regulations or methodology pages.
- Volunteering credit submission questions should prefer official volunteering/portfolio pages, not generic admission pages.
- Typo-based questions should still route to the correct faculty and page type.
- If evidence is weak, the answer should say that clearly and still show the best official sources found.

## Validation

Run fast automated tests after backend, retriever, index-schema, or API contract changes:

```powershell
python -m pytest
.\scripts\test.ps1
```

Run retrieval smoke tests after index, retriever, embedding, or Qdrant changes:

```powershell
python backend\scripts\smoke_retrieval.py
```

The smoke test is expected to fail if Ollama is not running, because query embeddings cannot be created and the retriever correctly falls back to local JSON lexical ranking instead of reporting Qdrant success.

Run backend health after backend changes:

```powershell
python backend\app.py
Invoke-RestMethod http://127.0.0.1:5000/health
```

Run the demo readiness check before presenting:

```powershell
python backend\scripts\demo_check.py
```

Run the RAG evaluation when the full local stack is up:

```powershell
python backend\scripts\evaluate_rag.py
```

Manual popup checklist:

1. `info` faculty, ask `Unde găsesc orarul?`; top source should be `info.uvt.ro/orare`.
2. `info` faculty, ask `Unde găsesc secretariatul Facultății de Informatică?`; top source should be `info.uvt.ro/contact`.
3. `uvt` faculty, ask `Este posibil ca un student să beneficieze de 2 burse?`; source should be a scholarship methodology/regulation page.
4. Ask `Unde găsesc informații despre admitere?`; returned sources should be official admission pages.
5. `info` faculty, ask `Unde găsesc orrarul la info?`; the Informatics schedule page should still win.
6. Stop Flask and open the popup; it should show the backend unavailable state.
7. Ask a vague or unsupported question; confidence should be low and sources should remain official.

## Limitations

- The system answers only from pages present in the local JSON/Qdrant index plus the narrow live verification step.
- The application depends on the quality, completeness, and freshness of the indexed official sources.
- If official pages change, the index must be rebuilt with `python backend\build_index.py`.
- If the embedding model changes, rebuild the Qdrant vector collection.
- Answer quality and latency depend on the local Ollama generation model and local hardware.
- Live fetching is intentionally bounded to keep the demo deterministic.
- OCR support is optional and depends on the separate OCR setup.
- The application is designed for local execution, not direct public exposure.
- The popup is the only user-facing interface; there is no separate web frontend.

## Securitate locala

- Aplicatia este proiectata pentru rulare locala: extensia Chrome comunica cu backendul Flask de pe `http://127.0.0.1:5000`.
- Ollama si Qdrant ruleaza local; intrebarile nu sunt trimise catre servicii externe AI.
- Feedbackul din popup este salvat local in `backend/feedback_log.jsonl`.
- Utilizatorul nu ar trebui sa introduca date personale sensibile in intrebari sau feedback.
- Nu expune backendul public fara CORS restrictiv, autentificare, rate limiting, limite de dimensiune pentru cereri, audit de logging si hardening general de deployment.
- `.env`, indexurile generate, evaluarile locale, stocarea Qdrant locala si logurile runtime sunt ignorate de Git.
