# Ghid de dezvoltare locala

Acest document descrie setup-ul local pentru dezvoltare si demo pe Windows PowerShell. Comenzile se ruleaza din radacina repository-ului.

## 1. Pregatire mediu Python

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
pip install -r requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

Fisierul `backend\.env` contine modelele Ollama, configurarea Qdrant, setarile de live verification, CORS si optiunile de indexare.

## 2. Rulare Ollama

Ollama trebuie sa fie instalat local si disponibil pe `http://127.0.0.1:11434`.

Porneste serverul intr-un terminal separat:

```powershell
ollama serve
```

In alt terminal, descarca modelele implicite:

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

Modelul `qwen3:4b` este folosit pentru generarea raspunsurilor, iar `nomic-embed-text` pentru embeddings. Daca schimbi modelul de embedding in `.env`, reconstruieste indexul vectorial.

## 3. Rulare Qdrant

Pentru demo si dezvoltare standard, porneste Qdrant prin Docker Compose:

```powershell
docker compose up -d qdrant
```

Verifica daca portul local este disponibil:

```powershell
Invoke-RestMethod http://127.0.0.1:6333/collections
```

Daca Docker nu este disponibil, se poate folosi stocarea locala Qdrant Client. In `backend\.env` seteaza:

```env
QDRANT_PATH=backend/data/qdrant_local
```

Pentru prezentare este recomandat modul Docker/server, deoarece starea colectiei este mai usor de verificat.

## 4. Build index

Build complet: crawler, snapshot JSON si index vectorial Qdrant.

```powershell
python backend\build_index.py
```

Build rapid numai pentru vectori, pornind de la `backend/data/page_index.json` existent:

```powershell
python backend\scripts\build_vector_index.py
```

Comenzi utile pentru dezvoltare:

```powershell
python backend\build_index.py --max-urls-per-faculty 90 --max-depth 2 --max-links-per-page 35 --fetch-workers 10
python backend\build_index.py --full-site
```

Reconstruieste indexul cand:

- se schimba modelul de embedding;
- se schimba crawlerul, chunking-ul sau schema indexului;
- se schimba lista de surse oficiale;
- vrei date mai proaspete pentru demo.

## 5. Rulare backend Flask

Porneste backendul:

```powershell
python backend\app.py
```

Verifica health:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

Verifica starea indexarii:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/indexing/status
```

Endpointurile publice sunt:

- `GET /health`
- `GET /faculties`
- `GET /indexing/status`
- `POST /chat`
- `POST /feedback`

## 6. Incarcare extensie Chrome

1. Deschide `chrome://extensions`.
2. Activeaza Developer mode.
3. Apasa Load unpacked.
4. Selecteaza folderul `extension/`.
5. Pastreaza pornite Ollama, Qdrant si backendul Flask.
6. Deschide popup-ul extensiei si trimite o intrebare.

Exemple pentru demo:

```text
Unde gasesc orarul?
Unde gasesc secretariatul facultatii de informatica?
Este posibil ca un student sa beneficieze de 2 burse?
Unde gasesc informatii despre admitere?
Unde gasesc orrarul la info?
```

## 7. Testare automata

Ruleaza compilarea Python:

```powershell
python -m compileall backend
```

Ruleaza toate testele:

```powershell
python -m pytest
```

Ruleaza smoke retrieval cand Ollama si Qdrant sunt disponibile:

```powershell
python backend\scripts\smoke_retrieval.py
```

Smoke retrieval este asteptat sa esueze daca Ollama sau Qdrant nu ruleaza, deoarece nu se pot crea embeddings si cautarea vectoriala nu poate fi validata.

## 8. Evaluare RAG

Cand stackul local este pornit complet:

```powershell
python backend\scripts\evaluate_rag.py
```

Rapoartele generate local sunt scrise in `backend/data/evaluation/`. Datasetul versionat de intrebari este `backend/evaluation/eval_questions.json` si nu trebuie modificat pentru a imbunatati artificial rezultatele.
