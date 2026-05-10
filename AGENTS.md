# AGENTS.md

Repository-specific guidance for future Codex runs on `UVT_Asist`.

## Product

- Chrome extension popup is the primary user interface.
- Flask backend is the only server component.
- Gemini remains the generation layer.
- Retrieval should stay local-index-first, with live fetch only as a narrow verification step.

## Important Files

- `backend/app.py`: request flow, response payload, feedback logging
- `backend/build_index.py`: crawler / index builder
- `backend/page_index.py`: index schema and chunking
- `backend/retriever.py`: ranking, routing, confidence logic
- `backend/live_fetch.py`: official page fetching and text extraction
- `backend/site_cache.py`: live verification cache
- `extension/popup.js`: popup states and API integration
- `extension/popup.css`: popup visual system

## Expectations

- Prefer improving retrieval quality over adding chatty UI behavior.
- Official source URLs and clean source cards are core product behavior.
- Policy / methodology questions should strongly prefer regulations and UVT-level sources.
- If retrieval is weak, be explicit instead of hallucinating.

## Validation

- Run `python backend\scripts\smoke_retrieval.py` after retriever changes.
- Run `python backend\app.py` and test `/health` after backend changes.
- Rebuild `backend/data/page_index.json` with `python backend\build_index.py` when crawl logic changes.

## Notes

- `backend/data/page_index.json` may exist in legacy page-level form; the loader upgrades it in memory.
- If Gemini is unavailable, backend responses fall back to a local evidence summary.
- Keep popup behavior extension-only; do not add a separate web frontend unless explicitly requested.
