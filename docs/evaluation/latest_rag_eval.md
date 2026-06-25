# Ultima evaluare RAG post-refactor

Acest document consemneaza verificarea RAG rulata dupa refactorizarile backend/RAG si dupa polish-ul UI al extensiei Chrome.

Evaluarea a fost rulata prin endpointul public `POST /chat`, nu prin apeluri directe catre functii interne. Astfel, rezultatul verifica traseul real folosit de extensia Chrome: Flask API, servicii, query analysis, Qdrant retrieval, reranking determinist si generare locala cu Ollama.

## Context rulare

- Data rularii: `2026-06-25`
- Backend: `http://127.0.0.1:5000`
- Dataset: `backend/evaluation/eval_qa_100.json`
- Script: `backend/scripts/evaluate_rag.py`
- Comanda folosita:

```powershell
python backend\scripts\evaluate_rag.py --questions backend/evaluation/eval_qa_100.json --timeout 180
```

Stack local folosit la momentul rularii:

- Ollama disponibil local;
- model generare: `qwen3:4b`;
- model embeddings: `nomic-embed-text`;
- Qdrant disponibil local;
- colectie Qdrant: `uvt_asist_chunks`;
- mod retrieval raportat de `/health`: `qdrant-vector-rag`;
- la momentul rularii istorice, live verification era activat;
- in versiunea curenta, live verification a fost eliminat din runtime, iar raspunsurile folosesc snapshotul local JSON/Qdrant.

## Rezumat rezultate

| Indicator | Valoare |
| --- | ---: |
| Intrebari evaluate | 100 |
| Raspunsuri primite | 100 |
| Erori de request | 0 |
| Confidence low | 21 |
| Top-1 URL match | 78 |
| Top-3 URL match | 78 |
| Intrebari fara raspuns sigur tratate corect | 10 |
| Latenta medie | 23.427s |
| Latenta mediana | 16.964s |

## Observatii

Evaluarea confirma ca aplicatia raspunde complet pe setul de 100 de intrebari in configuratia locala curenta, fara erori de request.

In urma verificarii a fost corectata o regresie in fallback-ul determinist de query analysis: atunci cand analiza cu Ollama nu oferea o intentie utila, intrebarile cu typo sau formulari simple puteau ramane pe `intent=general`. Dupa corectie, smoke retrieval confirma scenariile de demo pentru:

- orar Informatica;
- contact/secretariat Informatica;
- burse si regulamente;
- voluntariat;
- admitere;
- typo `orrarul`.

Singurul miss URL ramas in sumarul rularii este:

| ID | Comportament observat | Sursa asteptata |
| --- | --- | --- |
| `qa_calendar_006` | sistemul a cerut clarificarea facultatii, cu `confidence=low` si fara surse | `calendar`, `structura`, `uvt.ro` |

Acest caz nu este o eroare de executie, ci un caz de interpretare prudenta: intrebarea `Unde vad saptamanile de cursuri si sesiune?` a fost tratata ca necesitand clarificare.

## Artefacte locale

Rapoartele brute generate de evaluator au fost scrise local in `backend/data/evaluation/`:

- `eval_results_20260625T100823Z.json`
- `eval_results_20260625T100823Z.csv`
- `eval_summary_20260625T100823Z.md`

Directorul `backend/data/evaluation/` este ignorat de Git deoarece contine artefacte generate local. Acest document pastreaza in repository rezumatul stabil al rularii.

## Interpretare academica

Rezultatele trebuie interpretate ca o verificare pe datasetul definit in proiect si pe configuratia locala din momentul rularii. Ele nu sunt o garantie universala pentru orice intrebare posibila.

Raportul comparativ Q&A ramane documentul istoric pentru analiza inainte/dupa optimizari:

- [qa_before_after_stats.md](qa_before_after_stats.md)

Metodologia completa este descrisa in:

- [methodology.md](methodology.md)
