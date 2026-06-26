# Evaluare RAG si Q&A

Acest director pastreaza documentatia stabila pentru evaluarea proiectului. Rapoartele brute generate local raman in `backend/data/evaluation/` si sunt ignorate de Git.

Documente principale:

- [methodology.md](methodology.md): metodologia pentru evaluarea RAG, Q&A 100, Q&A 1000 si ablation study.
- [results.md](results.md): rezultatele consolidate pentru Q&A 1000, RAG post-refactor, comparatia Q&A 100 si latenta.
- [failure_analysis.md](failure_analysis.md): limite cunoscute, cazuri de refuz/clarificare si taxonomie pentru review manual.
- [qa1000_independent_latex_tables.tex](qa1000_independent_latex_tables.tex): tabele LaTeX generate din rezultatul final.
- [figures/](figures/): graficele Q&A 1000 folosite in raport si lucrare.

## Rulare evaluare RAG

Comanda recomandata:

```powershell
python backend/scripts/evaluate_rag.py
```

Rulare pe subset:

```powershell
python backend/scripts/evaluate_rag.py --limit 5
```

Rulare pe categorie:

```powershell
python backend/scripts/evaluate_rag.py --category burse
```

Rulare pe setul Q&A de 100 de intrebari cu evaluatorul RAG:

```powershell
python backend/scripts/evaluate_rag.py --questions backend/evaluation/eval_qa_100.json --timeout 180
```

## Rulare evaluare Q&A 100

Pentru comparatia Q&A cu 100 de intrebari si raspunsuri ideale:

```powershell
python backend/scripts/evaluate_qa.py
```

Datasetul folosit este `backend/evaluation/eval_qa_100.json`. Scorul Q&A combina potrivirea surselor, confidence-ul, acoperirea termenilor esentiali din raspunsul ideal si tratarea intrebarilor fara raspuns sigur.

## Rulare evaluare Q&A 1000

Aceasta evaluare este gandita ca evaluare finala pentru documentatie si pentru lucrarea de licenta. Scopul ei este colectarea de rezultate reproductibile pe un set independent, nu tuningul aplicatiei dupa rezultate.

Porneste serviciile locale:

```powershell
ollama serve
docker compose up -d qdrant
python backend/app.py
```

Test rapid:

```powershell
python backend/scripts/evaluate_qa_1000_independent.py --limit 10
```

Rulare completa:

```powershell
python backend/scripts/evaluate_qa_1000_independent.py --dataset backend/evaluation/eval_qa_1000_independent.json --backend-url http://127.0.0.1:5000 --timeout 180 --delay-ms 150 --run-label final_1000 --resume
```

Generare raport detaliat, CSV-uri si tabele LaTeX:

```powershell
python backend/scripts/report_qa_1000_independent.py --input backend/data/evaluation/<result_file>.json
```

Generare grafice:

```powershell
python backend/scripts/plot_qa1000_results.py --input backend/data/evaluation/<result_file>.json
```

## Artefacte generate

Rezultatele JSON, CSV si Markdown se salveaza in `backend/data/evaluation/`. Raportul detaliat regenerabil `docs/evaluation/qa1000_independent_report.md` este ignorat de Git; valorile stabile pastrate in repository sunt consolidate in [results.md](results.md).

Metricile principale sunt:

- pass rate;
- score mediu;
- median score;
- ideal overlap informativ;
- Top-1 URL match;
- Top-3 URL match;
- confidence match;
- unanswerable handled;
- latenta medie, mediana, p90 si p95.

Rezultatele sunt valabile pe setul definit si pe configuratia locala folosita la rulare, nu reprezinta garantie universala pentru orice intrebare posibila.
