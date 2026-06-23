# Structura proiectului UVT_Asist

Acest document explica organizarea codului din proiectul UVT_Asist. Scopul lui este sa arate comisiei de licenta cum este impartita aplicatia pe zone clare de responsabilitate, astfel incat codul sa fie usor de inteles, testat si extins.

Documentul completeaza descrierea arhitecturala din `docs/architecture.md`. Aici accentul este pus pe structura repository-ului si pe rolul directoarelor, nu pe fluxul complet RAG.

## Tree simplificat

```text
UVT_Asist/
|-- backend/
|   |-- app.py
|   |-- api/
|   |-- services/
|   |-- core/
|   |-- rag/
|   |   `-- ranking/
|   |-- scripts/
|   |-- tests/
|   |-- data/
|   |-- evaluation/
|   |-- build_index.py
|   |-- page_index.py
|   |-- vector_store.py
|   |-- vector_indexer.py
|   |-- ollama_client.py
|   `-- live_fetch.py
|-- extension/
|   |-- manifest.json
|   |-- popup.html
|   |-- popup.css
|   |-- popup.js
|   |-- options.html
|   |-- options.js
|   `-- js/
|       |-- api.js
|       |-- storage.js
|       |-- state.js
|       `-- render.js
|-- docs/
|   |-- architecture.md
|   |-- development.md
|   |-- project_structure.md
|   `-- evaluation/
|-- scripts/
|-- docker-compose.yml
|-- requirements-dev.txt
`-- README.md
```

## Backend

### `backend/app.py`

`backend/app.py` este entrypoint-ul Flask. El creeaza aplicatia prin `create_app()`, configureaza CORS, inregistreaza blueprint-urile HTTP si pastreaza compatibilitatea cu rularea directa:

```powershell
python backend/app.py
```

Fisierul ramane intentionat subtire. Logica de business este delegata catre servicii, iar rutele sunt definite separat in `backend/api/`.

### `backend/api/`

Directorul `backend/api/` contine rutele HTTP expuse de backend:

- `routes_health.py` pentru `GET /health`;
- `routes_faculties.py` pentru `GET /faculties`;
- `routes_indexing.py` pentru `GET /indexing/status`;
- `routes_chat.py` pentru `POST /chat`;
- `routes_feedback.py` pentru `POST /feedback`.

Responsabilitatea acestor fisiere este sa primeasca requestul, sa apeleze serviciul potrivit si sa returneze JSON-ul existent. Rutele nu trebuie sa contina logica RAG complexa.

### `backend/services/`

`backend/services/` contine logica aplicatiei care sta intre rutele Flask si modulele tehnice. Exemple:

- `chat_service.py` orchestreaza fluxul principal pentru `/chat`;
- `chat_request_parser.py`, `chat_guards.py`, `chat_cache.py` si `response_builder.py` separa parsing-ul, guard-urile, cache-ul si construirea raspunsului;
- `answer_generation_service.py` gestioneaza generarea raspunsului si fallback-urile locale;
- `source_navigation_service.py` construieste raspunsuri deterministe pentru intrebari de tip "unde gasesc";
- `feedback_service.py` salveaza feedbackul local;
- `health_service.py` construieste payloadul pentru `/health`;
- `indexing_service.py` tine starea indexarii de startup;
- `telemetry_service.py` scrie loguri JSONL privacy-friendly pentru requesturile `/chat`.

Aceasta zona contine regulile aplicatiei si coordoneaza modulele de infrastructura, dar nu ar trebui sa implementeze direct algoritmi de ranking.

### `backend/core/`

`backend/core/` contine componente generale folosite de backend:

- `config.py` centralizeaza citirea variabilelor de environment si valorile default;
- `logging.py` configureaza loggingul standard pentru backend.

Scopul este ca setarile runtime sa nu fie imprastiate prin rute sau servicii.

### `backend/rag/`

`backend/rag/` contine logica specializata pentru retrieval augmented generation:

- normalizare text si corectii de typo-uri;
- analiza determinista a query-ului;
- detectarea intentului;
- calculul confidence score;
- orchestrarea retrievalului semantic si lexical.

Acest pachet izoleaza logica RAG de stratul HTTP si de UI.

### `backend/rag/ranking/`

`backend/rag/ranking/` contine semnalele deterministe de ranking:

- `lexical.py` pentru potriviri lexicale;
- `faculty.py` pentru semnale legate de facultate;
- `page_type.py` pentru tipul paginii si pagini specifice;
- `policy.py` pentru intrebari despre regulamente, metodologii si politici.

Separarea acestor reguli ajuta la explicarea si testarea motivelor pentru care o sursa oficiala este preferata in fata alteia.

### `backend/scripts/`

`backend/scripts/` contine scripturi operationale pentru dezvoltare, demo si evaluare:

- reconstruirea indexului vectorial;
- smoke test pentru retrieval;
- verificare demo;
- evaluare RAG/Q&A;
- utilitare pentru inspectarea indexului.

Aceste scripturi sunt rulate local si nu fac parte din API-ul public al extensiei.

### `backend/tests/`

`backend/tests/` contine testele automate pytest. Testele sunt impartite in:

- teste unitare pentru normalizare, analiza query-ului, confidence, cache, guard-uri, telemetry si indexare;
- teste de integrare pentru contracte HTTP cu Flask test client;
- teste pentru datasetul de evaluare si utilitarele backend.

Testele rapide sunt concepute sa nu depinda de Ollama, Qdrant sau internet. Validarile care necesita stackul complet raman smoke/demo locale.

## Extensia Chrome

### `extension/`

`extension/` contine interfata utilizatorului. Extensia este incarcata in Chrome cu "Load unpacked" si ramane singura interfata publica a produsului.

Elementele principale sunt:

- `manifest.json`, configuratia Manifest V3;
- `popup.html`, structura popup-ului;
- `popup.css`, stilurile UI;
- `popup.js`, initializarea popup-ului si coordonarea modulelor JS;
- `options.html` si `options.js`, pagina de optiuni pentru configurarea URL-ului backend local.

Extensia nu contine logica RAG. Ea trimite requesturi catre backend si afiseaza raspunsurile, sursele, confidence score si feedbackul.

### `extension/js/`

`extension/js/` imparte codul popup-ului in module simple, fara bundler si fara framework frontend:

- `api.js` comunica cu backendul Flask;
- `storage.js` gestioneaza `chrome.storage.local`, URL-ul backend, istoricul si tema;
- `state.js` tine state-ul conversatiei;
- `render.js` creeaza elementele DOM pentru mesaje, surse, badge-uri si feedback.

Aceasta impartire pastreaza extensia usor de incarcat direct in Chrome, dar evita un `popup.js` monolitic.

## Documentatie si comenzi locale

### `docs/`

`docs/` contine documentatia tehnica si academica a proiectului:

- arhitectura generala;
- ghid de dezvoltare locala;
- structura proiectului;
- metodologie de evaluare;
- cazuri de esec;
- note de latenta;
- plan de ablation study;
- checklist pentru demo.

Documentatia este folosita atat pentru dezvoltare, cat si pentru explicarea proiectului in lucrarea de licenta.

### `scripts/`

`scripts/` contine wrapper-e PowerShell pentru Windows:

- setup mediu virtual;
- pornire Qdrant;
- build index;
- rulare backend;
- smoke retrieval;
- teste;
- evaluare RAG.

Aceste scripturi nu inlocuiesc comenzile Python existente, ci le fac mai usor de rulat pentru demo si dezvoltare.

## De ce este separata aplicatia pe layere

Separarea pe layere reduce cuplarea dintre interfata, API, logica aplicatiei si logica RAG.

- Rutele HTTP sunt subtiri. Ele se ocupa de request/response si delega imediat catre servicii.
- Serviciile contin logica aplicatiei. Aici sunt tratate cache-ul, guard-urile, feedbackul, telemetry, raspunsurile fallback si orchestrarea `/chat`.
- Pachetul `rag` contine logica de retrieval si ranking. Selectia surselor ramane determinista si testabila, separata de Flask si de extensie.
- `core` contine configurare si logging. Variabilele de environment si setup-ul de logging sunt centralizate.
- Extensia Chrome este doar UI. Ea nu decide surse, nu face ranking si nu genereaza raspunsuri; doar afiseaza rezultatul primit de la backend.

Aceasta organizare face proiectul mai matur software: componentele pot fi testate separat, endpointurile publice raman stabile, iar modificarile viitoare pot fi facute fara rescrierea intregii aplicatii.
