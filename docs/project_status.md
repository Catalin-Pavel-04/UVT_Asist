# Raport tehnic final - starea proiectului UVT_Asist

Acest raport sintetizeaza starea curenta a proiectului UVT_Asist inainte de predare si demo-ul de licenta. Documentul foloseste informatii existente in repository si trebuie citit impreuna cu documentatia tehnica detaliata:

- [Arhitectura tehnica](architecture.md)
- [Ghid de dezvoltare locala](development.md)
- [Metodologie evaluare RAG](evaluation/methodology.md)
- [Raport comparativ Q&A](evaluation/qa_before_after_stats.md)
- [Checklist demo](demo_checklist.md)

## Rezumat aplicatie

UVT_Asist este o aplicatie RAG locala pentru intrebari studentesti despre informatii oficiale ale Universitatii de Vest din Timisoara. Interfata utilizatorului este o extensie Chrome, iar procesarea se face intr-un backend Flask local.

Aplicatia foloseste:

- surse oficiale UVT si ale facultatilor;
- index JSON local al paginilor si chunkurilor;
- embeddings locale prin Ollama;
- Qdrant pentru cautare vectoriala locala;
- reranking determinist pentru selectia surselor;
- verificare live limitata pentru sursele de top;
- generare raspuns cu Ollama local;
- confidence score, surse oficiale si metadata de evidence in raspuns.

Scopul proiectului este sa ofere un asistent demonstrabil academic, local-first, care raspunde numai pe baza surselor oficiale disponibile si trateaza prudent intrebarile vagi, personale sau speculative.

## Arhitectura actuala

Arhitectura curenta este impartita pe layere:

- `extension/`: interfata Chrome folosita de student;
- `backend/app.py`: entrypoint Flask, `create_app()`, CORS si inregistrare blueprinturi;
- `backend/api/`: rute HTTP subtiri;
- `backend/services/`: logica aplicatiei, chat orchestration, feedback, health, indexing si telemetry;
- `backend/core/`: configurare runtime si logging;
- `backend/rag/`: normalizare, analiza query, intent, confidence si retrieval orchestration;
- `backend/rag/ranking/`: scoring lexical, faculty, page type si policy;
- `backend/scripts/`: scripturi locale de build, smoke, demo check si evaluare;
- `backend/tests/`: teste pytest unitare si de integrare;
- `docs/`: documentatie tehnica si academica;
- `scripts/`: wrapper-e PowerShell pentru dezvoltare si demo.

Rutele HTTP raman stabile, iar logica reala este mutata in servicii si module RAG specializate. Aceasta separare face codul mai usor de explicat, testat si mentinut.

## Ce componente sunt implementate

Componente backend implementate:

- API Flask cu endpointuri publice stabile;
- configurare centralizata prin `.env` si `backend/core/config.py`;
- logging standard si telemetry JSONL pentru requesturile `/chat`;
- crawler si indexare surse oficiale;
- chunking pentru pagini HTML si documente;
- vector index in Qdrant;
- client Ollama pentru chat si embeddings;
- retriever semantic cu fallback lexical;
- reranking determinist;
- cache de raspunsuri;
- guard-uri pentru intrebari goale, vagi, unsupported sau in timpul indexarii;
- feedback local in format JSONL;
- teste pytest offline pentru zone critice.

Componente extensie implementate:

- popup Chrome Manifest V3;
- selector de facultate;
- status backend si progres indexare;
- intrebari rapide;
- intrebari recente;
- istoric per facultate;
- afisare raspuns, confidence, surse si detalii tehnice;
- feedback `Util` / `Inexact`;
- dark/light theme;
- copiere raspuns;
- stergere conversatie;
- pagina de optiuni pentru backend URL local.

## Ce ruleaza local

Aplicatia este proiectata pentru rulare locala:

- Flask backend: `http://127.0.0.1:5000`;
- Ollama: `http://127.0.0.1:11434`;
- Qdrant: `http://127.0.0.1:6333`;
- extensia Chrome comunica local cu backendul;
- intrebarile nu sunt trimise catre servicii externe AI;
- feedbackul si telemetry sunt salvate local.

Modelele implicite din configuratie sunt:

- `qwen3:4b` pentru generare;
- `nomic-embed-text` pentru embeddings.

## Endpointuri backend

Endpointurile publice pastrate sunt:

- `GET /health`: raporteaza starea Ollama, Qdrant, index JSON, vector index, cache-uri si startup indexing;
- `GET /faculties`: returneaza lista de facultati configurate;
- `GET /indexing/status`: returneaza progresul indexarii de startup;
- `POST /chat`: primeste intrebarea, facultatea si istoricul, apoi returneaza raspunsul RAG;
- `POST /feedback`: salveaza feedback local.

Payloadurile JSON sunt folosite de extensia Chrome si trebuie pastrate compatibile.

## Structura extensiei Chrome

Extensia ramane fara build system, fara React si fara bundler. Se incarca direct cu `Load unpacked`.

Structura principala:

- `extension/manifest.json`: Manifest V3 si permisiuni locale;
- `extension/popup.html`: markup popup;
- `extension/popup.css`: stiluri UI;
- `extension/popup.js`: initializare, event listeners si coordonare;
- `extension/options.html` si `extension/options.js`: configurarea URL-ului backend local;
- `extension/js/api.js`: comunicare cu backendul Flask;
- `extension/js/storage.js`: `chrome.storage.local`, backend URL, tema, istoric, intrebari recente;
- `extension/js/state.js`: state-ul conversatiei;
- `extension/js/render.js`: randare mesaje, surse, badge-uri, detalii tehnice si feedback.

Extensia este doar UI. Ea nu face retrieval, ranking sau generare de raspunsuri.

## Structura RAG

Fluxul RAG este local-index-first:

1. intrebarea este normalizata;
2. typo-urile frecvente sunt corectate;
3. este detectata intentia;
4. sunt detectate intrebarile de tip regulament/metodologie;
5. query-ul este embedat local prin Ollama;
6. Qdrant returneaza candidati vectoriali;
7. candidatii sunt rerankati determinist;
8. backendul calculeaza confidence si evidence;
9. raspunsul este generat local cu Ollama sau, pentru unele intrebari de navigare, local determinist.

Selectia surselor nu este delegata LLM-ului. Sursele sunt alese de retrieval si reranking deterministic, iar modelul generativ primeste doar contextul oficial selectat.

## Evaluare si teste

Proiectul include doua directii de evaluare:

- evaluarea RAG din `backend/evaluation/eval_questions.json`, rulata cu `backend/scripts/evaluate_rag.py`;
- evaluarea Q&A 100 din `backend/evaluation/eval_qa_100.json`, rulata cu `backend/scripts/evaluate_qa.py`.

Metodologia este descrisa in [docs/evaluation/methodology.md](evaluation/methodology.md). Rezultatele trebuie interpretate ca rezultate pe seturile definite in proiect, nu ca garantii universale pentru orice intrebare posibila.

Raportul comparativ existent [qa_before_after_stats.md](evaluation/qa_before_after_stats.md) consemneaza, pe setul de 100 de intrebari:

- rata de trecere: 65% inainte, 100% dupa optimizari;
- scor mediu Q&A: 69.54 inainte, 85.84 dupa optimizari;
- Top-1 URL corect: 98/100 inainte, 100/100 dupa optimizari;
- Top-3 URL corect: 98/100 inainte, 100/100 dupa optimizari;
- potrivire nivel incredere: 83/100 inainte, 99/100 dupa optimizari;
- intrebari fara raspuns sigur tratate corect: 1/10 inainte, 10/10 dupa optimizari;
- latenta medie: 27.182s inainte, 13.679s dupa optimizari;
- latenta mediana: 37.689s inainte, 4.342s dupa optimizari.

Aceste valori sunt istorice si apartin rapoartelor locale mentionate in acel document. Ele nu trebuie prezentate ca evaluare globala absoluta.

Testarea automata locala se ruleaza cu:

```powershell
python -m compileall backend
python -m pytest
```

Exista si workflow GitHub Actions pentru testele rapide/offline, fara Ollama, Qdrant sau Docker.

## Logging si privacy

Aplicatia foloseste logging local:

- feedbackul este salvat local in `backend/feedback_log.jsonl`;
- telemetry pentru `/chat` este salvata in `backend/logs/chat_requests.jsonl`;
- logul de telemetry nu salveaza intrebarea completa, ci doar lungimea intrebarii si metadata precum intent, retrieval backend, generation mode, confidence, surse si latenta.

Designul privacy-friendly este local-first:

- nu sunt folosite API-uri AI externe in runtime;
- Ollama si Qdrant ruleaza local;
- utilizatorul este sfatuit sa nu introduca date personale sensibile;
- backendul nu este gandit pentru expunere publica fara hardening suplimentar.

## Comenzi de rulare

Setup initial:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
pip install -r requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

Pornire servicii locale:

```powershell
ollama serve
docker compose up -d qdrant
```

Build index:

```powershell
python backend\build_index.py
```

Rebuild doar vector index:

```powershell
python backend\scripts\build_vector_index.py
```

Pornire backend:

```powershell
python backend\app.py
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

Verificare rapida:

```powershell
.\scripts\final_check.ps1
```

Verificare completa cu stack local:

```powershell
.\scripts\final_check.ps1 -FullStack
```

## Limitari cunoscute

Limitari importante:

- calitatea raspunsului depinde de sursele oficiale indexate;
- daca site-urile UVT se schimba, indexul trebuie reconstruit;
- daca modelul de embedding se schimba, Qdrant trebuie reconstruit;
- raspunsurile reflecta snapshotul local al surselor oficiale;
- documentele mari sau PDF-urile pot produce latente mai mari;
- Ollama si Qdrant trebuie sa ruleze local pentru demo complet;
- backendul este proiectat local, nu ca serviciu public;
- evaluarile masoara seturile definite in proiect, nu toate intrebarile posibile;
- OCR este optional si depinde de configurarea separata.

Pentru demo predictibil, indexul trebuie reconstruit inainte de prezentare daca sursele oficiale s-au schimbat.

## Ce trebuie verificat inainte de demo

Checklist minim:

- `.venv` exista si are dependintele instalate;
- `backend/.env` este actualizat fata de `.env.example`;
- Ollama ruleaza;
- modelele `qwen3:4b` si `nomic-embed-text` sunt instalate;
- Qdrant ruleaza;
- `backend/data/page_index.json` exista;
- colectia Qdrant are puncte indexate;
- `python -m pytest` trece;
- `python backend/scripts/smoke_retrieval.py` trece cu Qdrant disponibil;
- `python backend/scripts/demo_check.py` nu raporteaza erori critice;
- `python backend/app.py` porneste fara erori;
- `/health` raporteaza starea componentelor locale;
- extensia este reincarcata in Chrome;
- backend URL-ul extensiei este `http://127.0.0.1:5000`;
- intrebarile recomandate din [demo_checklist.md](demo_checklist.md) functioneaza.

Pentru prezentare, este util sa ai deschise:

- terminal cu `ollama serve`;
- terminal cu backendul Flask;
- Chrome cu extensia incarcata;
- pagina `/health` sau outputul `demo_check.py`;
- documentul [demo_checklist.md](demo_checklist.md).
