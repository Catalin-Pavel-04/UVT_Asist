# Checklist final pentru demo-ul de licenta

Acest checklist este gandit pentru rularea demonstratiei locale UVT_Asist in fata comisiei. Pasii presupun ca proiectul este deschis in root-ul repository-ului si ca lucrezi pe Windows PowerShell.

## Inainte de demo

- [ ] Activeaza mediul virtual Python:

```powershell
.venv\Scripts\activate
python --version
```

- [ ] Verifica existenta fisierului `backend\.env`:

```powershell
Test-Path backend\.env
```

- [ ] Verifica setarile importante din `.env`:

```powershell
Get-Content backend\.env | Select-String "OLLAMA_GENERATION_MODEL|OLLAMA_EMBEDDING_MODEL|QDRANT|ALLOWED_CORS_ORIGINS"
```

- [ ] Verifica daca Ollama raspunde:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

- [ ] Verifica modelele Ollama necesare:

```powershell
ollama list
```

Modelele asteptate pentru configuratia implicita sunt:

- `qwen3:4b`
- `nomic-embed-text`

Daca lipsesc, ruleaza:

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

- [ ] Verifica Qdrant:

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:6333/collections
```

- [ ] Verifica indexul JSON:

```powershell
Test-Path backend\data\page_index.json
```

Daca lipseste sau este vechi, reconstruieste indexul:

```powershell
python backend\build_index.py
```

- [ ] Verifica vector indexul Qdrant prin health check sau scriptul demo:

```powershell
python backend\scripts\demo_check.py
```

- [ ] Ruleaza testele rapide offline:

```powershell
python -m pytest
```

- [ ] Ruleaza smoke retrieval, dupa ce Ollama si Qdrant sunt pornite:

```powershell
python backend\scripts\smoke_retrieval.py
```

- [ ] Ruleaza verificarea generala de demo:

```powershell
python backend\scripts\demo_check.py
```

## Pornire demo

Deschide terminale separate pentru serviciile care trebuie sa ramana pornite.

1. Porneste Ollama:

```powershell
ollama serve
```

2. Porneste Qdrant:

```powershell
docker compose up -d qdrant
```

3. Activeaza mediul virtual si porneste backendul Flask:

```powershell
.venv\Scripts\activate
python backend\app.py
```

4. Verifica endpointul `/health`:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

In raspuns, urmareste in special:

- `ready`;
- `retrieval_mode`;
- `checks.ollama`;
- `checks.generation_model`;
- `checks.embedding_model`;
- `checks.json_index`;
- `checks.qdrant_index`;
- `vector_index.points_count`.

5. Incarca extensia Chrome:

- deschide `chrome://extensions`;
- activeaza Developer mode;
- apasa Load unpacked;
- selecteaza folderul `extension/`;
- deschide popup-ul extensiei UVT_Asist.

6. Daca backend URL-ul nu este cel implicit, deschide pagina de optiuni a extensiei si seteaza:

```text
http://127.0.0.1:5000
```

## Intrebari recomandate

Foloseste aceste intrebari pentru a demonstra scenarii diferite: navigare, facultate specifica, regulament, admitere si corectie typo.

- [ ] Facultate `info`: `Unde gasesc orarul?`

Comportament asteptat: sursa oficiala de tip orar, preferabil `info.uvt.ro/orare`.

- [ ] Facultate `info`: `Unde gasesc secretariatul facultatii de informatica?`

Comportament asteptat: pagina oficiala de contact/secretariat pentru Informatica.

- [ ] Facultate `uvt`: `Este posibil ca un student sa beneficieze de 2 burse?`

Comportament asteptat: surse oficiale despre burse, metodologie sau regulament.

- [ ] Facultate `uvt`: `Unde gasesc informatii despre admitere?`

Comportament asteptat: pagini oficiale UVT de admitere.

- [ ] Facultate `info`: `Unde gasesc orrarul la info?`

Comportament asteptat: sistemul corecteaza typo-ul `orrarul` si prefera pagina oficiala de orar.

## Ce trebuie sa observ in UI

- [ ] Raspunsul afisat este concis si in romana.
- [ ] Cardurile de surse contin URL-uri oficiale UVT sau ale facultatilor.
- [ ] Badge-ul de `confidence` este vizibil si coerent cu raspunsul.
- [ ] UI-ul indica daca raspunsul vine din index local si/sau verificare live.
- [ ] Elementul `Detalii tehnice` poate fi deschis pentru informatii despre retrieval, intent si generation mode.
- [ ] Butoanele de feedback `Util` si `Inexact` sunt disponibile dupa raspuns.
- [ ] Butonul de copiere raspuns copiaza ultimul raspuns al asistentului.
- [ ] Butonul de stergere conversatie curata istoricul curent.
- [ ] Daca backendul este oprit, extensia afiseaza starea de backend indisponibil, nu ramane blocata.

## Probleme frecvente

### Ollama nu ruleaza

Simptom: `/health` raporteaza Ollama indisponibil sau intrebarile nu pot fi generate.

Rezolvare:

```powershell
ollama serve
```

### Modelul Ollama lipseste

Simptom: `/health` raporteaza `generation_model=false` sau `embedding_model=false`.

Rezolvare:

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

### Qdrant nu ruleaza

Simptom: `/health` raporteaza `qdrant_index=false` sau smoke retrieval nu foloseste Qdrant.

Rezolvare:

```powershell
docker compose up -d qdrant
Invoke-RestMethod http://127.0.0.1:6333/collections
```

### Indexul lipseste

Simptom: `/health` raporteaza `json_index=false`, `qdrant_index=false` sau `points_count=0`.

Rezolvare:

```powershell
python backend\build_index.py
```

Daca exista deja `backend\data\page_index.json`, dar lipseste doar vector indexul:

```powershell
python backend\scripts\build_vector_index.py
```

### CORS sau extensia nu comunica cu backendul

Simptom: popup-ul spune ca backendul este indisponibil, desi Flask ruleaza.

Verificari:

- backendul ruleaza pe `http://127.0.0.1:5000`;
- extensia are backend URL setat la `http://127.0.0.1:5000`;
- `backend\.env` contine origini locale in `ALLOWED_CORS_ORIGINS`;
- `extension/manifest.json` are host permissions pentru `127.0.0.1` si `localhost`.

Pentru demo local, valoarea obisnuita este:

```env
ALLOWED_CORS_ORIGINS=http://127.0.0.1:5000,http://localhost:5000
```

Daca browserul cere explicit origin de extensie, se poate adauga temporar pentru demo local:

```env
ALLOWED_CORS_ORIGINS=http://127.0.0.1:5000,http://localhost:5000,chrome-extension://*
```

### Raspunsurile par invechite

Simptom: raspunsurile sunt coerente, dar nu reflecta o modificare recenta de pe site-urile oficiale.

Runtime-ul foloseste snapshotul local JSON/Qdrant. Reconstruieste indexul inainte de demo daca sursele oficiale s-au schimbat:

```powershell
python backend\build_index.py
```

Dupa rebuild, reporneste backendul Flask.

## Secventa scurta chiar inainte de prezentare

Ruleaza aceste comenzi in ordine:

```powershell
.venv\Scripts\activate
docker compose up -d qdrant
ollama list
python -m pytest
python backend\scripts\demo_check.py
python backend\scripts\smoke_retrieval.py
python backend\app.py
```

Apoi verifica in browser:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

In final, deschide extensia Chrome si testeaza intrebarea:

```text
Unde gasesc orarul?
```
