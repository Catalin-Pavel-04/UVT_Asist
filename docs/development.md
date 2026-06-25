# Ghid de dezvoltare locala

Acest document descrie setup-ul local pentru dezvoltare si demo pe Windows PowerShell. Comenzile se ruleaza din radacina repository-ului.

## Comenzi rapide

Repository-ul include wrapper-e PowerShell in `scripts/`, fara sa inlocuiasca scripturile Python existente. Comenzile principale raman functionale:

```powershell
python backend\app.py
python backend\build_index.py
```

Pentru Windows, fluxul recomandat este:

```powershell
.\scripts\setup.ps1
.\scripts\start_qdrant.ps1
.\scripts\build_index.ps1
.\scripts\run_backend.ps1
```

In alt terminal ruleaza manual Ollama:

```powershell
ollama serve
```

Wrapper-ele disponibile:

```powershell
.\scripts\setup.ps1                 # venv, requirements, requirements-dev, .env daca lipseste
.\scripts\start_qdrant.ps1          # docker compose up -d qdrant
.\scripts\build_index.ps1           # crawler + JSON + Qdrant vectors
.\scripts\build_index.ps1 -VectorOnly
.\scripts\run_backend.ps1           # porneste Flask
.\scripts\smoke.ps1                 # smoke retrieval
.\scripts\smoke.ps1 -DemoCheck      # smoke retrieval + demo_check
.\scripts\test.ps1                  # compileall + pytest
.\scripts\test.ps1 -Coverage
.\scripts\test.ps1 -EvaluateRag     # ruleaza si evaluarea RAG, daca scriptul exista
.\scripts\final_check.ps1           # verificare rapida inainte de demo
.\scripts\final_check.ps1 -FullStack # include smoke_retrieval si demo_check
```

Exista si un `Makefile` pentru medii unde `make` este disponibil:

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

## 1. Pregatire mediu Python

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
pip install -r requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

Fisierul `backend\.env` contine modelele Ollama, configurarea Qdrant, CORS, cache-uri si optiunile de indexare.

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

Echivalent prin wrapper:

```powershell
.\scripts\build_index.ps1
.\scripts\build_index.ps1 -VectorOnly
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

Echivalent prin wrapper:

```powershell
.\scripts\run_backend.ps1
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

## 6. Logging structurat pentru chat

Fiecare request `POST /chat` primeste intern un `request_id` si este logat local in format JSONL:

```text
backend/logs/chat_requests.jsonl
```

Folderul `backend/logs/` este ignorat de Git. Logul este util pentru analiza tehnica a executiei unei intrebari in lucrarea de licenta, fara sa salveze intrebarea completa. Pentru confidentialitate, se salveaza doar `question_length`.

Fiecare linie contine metadate precum:

- `timestamp`
- `request_id`
- `question_length`
- `faculty_id`
- `matched_faculty_id`
- `detected_intent`
- `retrieval_backend`
- `generation_mode`
- `confidence`
- `confidence_score`
- `source_count`
- `verified_source_count` si `live_verified`, pastrate pentru compatibilitatea payloadului; in configuratia curenta raman `0` si `false`, deoarece raspunsurile vin din indexul local.
- `total_latency_ms`
- `generation_error`, cand exista

Exemplu de inspectare rapida:

```powershell
Get-Content backend\logs\chat_requests.jsonl -Tail 5
```

## 7. Incarcare extensie Chrome

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

## 8. CORS si extensia Chrome

Backendul Flask aplica CORS doar pe endpointurile publice ale aplicatiei si accepta numai originile configurate in `ALLOWED_CORS_ORIGINS`. Defaultul este local-first:

```env
ALLOWED_CORS_ORIGINS=http://127.0.0.1:5000,http://localhost:5000
```

Extensia Chrome are `host_permissions` pentru:

```json
"http://127.0.0.1:5000/*",
"http://localhost:5000/*"
```

In scenariul normal `Load unpacked`, popup-ul extensiei poate face requesturi catre backendul local daca URL-ul din optiunile extensiei este `http://127.0.0.1:5000` sau `http://localhost:5000`.

Daca browserul blocheaza requestul cu o eroare CORS in timpul unui demo local, verifica:

- backendul ruleaza pe `127.0.0.1:5000`;
- URL-ul din optiunile extensiei este local;
- `backend\.env` contine originile locale in `ALLOWED_CORS_ORIGINS`;
- daca este necesar pentru demo, adauga doar wildcardul de extensie Chrome:

```env
ALLOWED_CORS_ORIGINS=http://127.0.0.1:5000,http://localhost:5000,chrome-extension://*
```

Nu adauga origini web publice si nu folosi wildcard extern. Proiectul este gandit pentru rulare locala, nu pentru expunere publica.

## 9. Testare automata

Ruleaza compilarea Python:

```powershell
python -m compileall backend
```

Ruleaza toate testele:

```powershell
python -m pytest
```

Echivalent prin wrapper:

```powershell
.\scripts\test.ps1
```

Verificare finala rapida inainte de demo:

```powershell
.\scripts\final_check.ps1
```

Verificare completa dupa ce Ollama si Qdrant sunt pornite:

```powershell
.\scripts\final_check.ps1 -FullStack
```

Ruleaza smoke retrieval cand Ollama si Qdrant sunt disponibile:

```powershell
python backend\scripts\smoke_retrieval.py
```

Echivalent prin wrapper:

```powershell
.\scripts\smoke.ps1
```

Smoke retrieval este asteptat sa esueze daca Ollama sau Qdrant nu ruleaza, deoarece nu se pot crea embeddings si cautarea vectoriala nu poate fi validata.

## 10. Evaluare RAG

Cand stackul local este pornit complet:

```powershell
python backend\scripts\evaluate_rag.py
```

Echivalent prin wrapper:

```powershell
.\scripts\test.ps1 -EvaluateRag
```

Rapoartele generate local sunt scrise in `backend/data/evaluation/`. Datasetul versionat de intrebari este `backend/evaluation/eval_questions.json` si nu trebuie modificat pentru a imbunatati artificial rezultatele.
