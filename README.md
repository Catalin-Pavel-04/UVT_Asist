# UVT_Asist

`UVT_Asist` is a Chrome extension plus Flask backend that answers student questions using a local RAG-style index built from official UVT and faculty websites. Retrieval is index-first, faculty-aware, page-type-aware, and optimized for a bachelor thesis demo.

## What Changed

- Local knowledge base is now chunk-first instead of page-first.
- Retrieval uses query normalization, typo correction, intent detection, policy-question routing, metadata boosts, and local confidence scoring.
- Live fetching still exists, but only for top candidate pages.
- The popup now exposes backend state, confidence, routing hints, verified-source badges, recent questions, and structured official source cards.
- Feedback is logged in a thesis-friendly JSONL format.

## Current Retrieval Flow

1. Normalize the user question.
2. Correct common Romanian student typos and wording variants.
3. Detect intent: `orar`, `burse`, `contact`, `admitere`, `regulamente`, `studenti`, `general`.
4. Detect policy-style questions such as cumulation / eligibility / methodology questions.
5. Route by selected faculty and preferred page types.
6. Retrieve the best local chunks from `backend/data/page_index.json`.
7. Live-verify only the best source URLs.
8. Send the strongest official evidence to Gemini.
9. Return answer + confidence + clean source cards.

## Index Format

The local index lives in `backend/data/page_index.json` and stores chunk records with:

- `chunk_id`
- `faculty_id`
- `page_type`
- `title`
- `url`
- `chunk_text`
- `last_indexed`

Legacy page-level index files are upgraded automatically in memory when loaded.

## Project Structure

- `backend/app.py`: Flask API and chat orchestration
- `backend/build_index.py`: deterministic crawler + chunk index builder
- `backend/page_index.py`: index schema, chunking, page typing, legacy upgrade
- `backend/retriever.py`: hybrid retrieval, routing, typo handling, confidence scoring
- `backend/live_fetch.py`: fetch + text extraction for HTML / PDF / DOCX / OCR images
- `backend/site_cache.py`: top-source live verification cache
- `backend/prompts.py`: Gemini system/user prompts
- `extension/popup.*`: Chrome extension UI
- `backend/scripts/smoke_retrieval.py`: local retrieval smoke checks

## Setup

### 1. Install backend dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
```

### 2. Configure Gemini

Create `backend/.env` with:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

If `GEMINI_API_KEY` is missing, the backend still returns a local evidence fallback answer, but full thesis demos should use Gemini.

### 3. Build or rebuild the local index

```powershell
python backend\build_index.py
```

Optional crawl controls:

```powershell
python backend\build_index.py --max-urls-per-faculty 90 --max-depth 2 --max-links-per-page 35 --fetch-workers 10
```

The builder prioritizes:

- `/orare/`
- `/burse/`
- `/contact/`
- `/studenti/`
- `/admitere/`
- `/regulamente/`
- `/metodologii/`
- `/proceduri/`

### 4. Run Flask

```powershell
python backend\app.py
```

Health endpoint:

```text
http://127.0.0.1:5000/health
```

### 5. Load the Chrome extension

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Choose `Load unpacked`
4. Select the `extension/` folder

## Local Validation

### Retrieval smoke test

```powershell
python backend\scripts\smoke_retrieval.py
```

This validates the local ranking behavior without needing the extension UI.

### Manual extension / API checklist

Use these scenarios after Flask is running:

1. Faculty = `info`, question = `Unde gasesc orarul?`
Expected: `https://info.uvt.ro/orare` or `https://info.uvt.ro/orar` is preferred.

2. Faculty = `info`, question = `Unde gasesc secretariatul facultatii de informatica?`
Expected: `https://info.uvt.ro/contact` is preferred over other faculties.

3. Faculty = `uvt`, question = `Este posibil sa beneficiezi de 2 burse?`
Expected: regulations / methodology pages are preferred over random faculty bursary pages.

4. Faculty = `uvt`, question = `Unde gasesc informatii despre admitere?`
Expected: admitere pages are returned, with official sources exposed clearly.

5. Faculty = `info`, question = `Unde gasesc orrarul la info?`
Expected: typo is normalized and the Informatics schedule pages still win.

6. Faculty = any, backend stopped
Expected: popup shows backend unavailable state instead of hanging silently.

## Logging

Feedback is appended to:

```text
backend/feedback_log.jsonl
```

Each record stores:

- question
- selected faculty
- matched faculty
- answer
- confidence
- confidence score
- feedback vote
- sources
- timestamp

## Notes For Thesis Demo

- Rebuild the index before the live demo to refresh official sources.
- Keep Flask running locally before opening the popup.
- Use the extension popup as the primary interface.
- For demo reliability, verify `/health` first and keep a valid `GEMINI_API_KEY` configured.
