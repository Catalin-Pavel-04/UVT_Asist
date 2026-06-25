# Rezultatele evaluarii RAG

Rezultatele brute generate local raman in `backend/data/evaluation/` si sunt ignorate de Git. Pentru lucrarea de licenta, pastreaza in repository doar rezumatele stabile sau valorile finale folosite in documentatie.

Documente utile:

- [methodology.md](methodology.md): metodologia evaluarii RAG si Q&A.
- [latest_rag_eval.md](latest_rag_eval.md): ultima evaluare RAG post-refactor pe setul de 100 de intrebari.
- [qa_before_after_stats.md](qa_before_after_stats.md): raport comparativ Q&A inainte/dupa optimizari.
- [ablation_plan.md](ablation_plan.md): plan pentru ablation study.
- [failure_cases.md](failure_cases.md): exemple de refuz controlat si clarificari.
- [latency_notes.md](latency_notes.md): interpretarea latentei.

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

## Rulare evaluare Q&A

Pentru comparatia Q&A cu 100 de intrebari si raspunsuri ideale:

```powershell
python backend/scripts/evaluate_qa.py
```

Datasetul folosit este `backend/evaluation/eval_qa_100.json`. Scorul Q&A combina potrivirea surselor, confidence-ul, acoperirea termenilor esentiali din raspunsul ideal si tratarea intrebarilor fara raspuns sigur.

## Evaluare independenta Q&A pe 1000 de intrebari

Aceasta evaluare este gandita ca evaluare finala pentru documentatie si pentru lucrarea de licenta. Scopul ei este colectarea de rezultate reproductibile pe un set independent, nu tuningul sau optimizarea aplicatiei dupa rezultate.

Datasetul are 1000 de intrebari, grupate in 10 categorii cu cate 100 de intrebari per categorie. Intrebarile sunt independente si generate in afara Codex. Fiecare intrebare include o rubrica `ideal_answer` si criterii de scoring precum `expected_url_contains`, `expected_confidence`, `required_terms` si `forbidden_terms`.

`ideal_answer` nu este comparat exact text-la-text, deoarece pot exista mai multe formulari corecte ale aceluiasi raspuns. Evaluatorul masoara semnale verificabile: sursa oficiala returnata, confidence-ul, termenii obligatorii, termenii interzisi si tratarea prudenta a incertitudinii.

Inainte de rulare, pornesc serviciile locale:

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

Generare raport pentru documentatie si LaTeX:

```powershell
python backend/scripts/report_qa_1000_independent.py --input backend/data/evaluation/<result_file>.json
```

Rezultatele JSON, CSV si Markdown se salveaza in `backend/data/evaluation/`. Raportul curat si tabelele LaTeX se genereaza in `docs/evaluation/`.

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

## Metrici recomandate pentru raportare

- total questions;
- top-1 URL match;
- top-3 URL match;
- low confidence count;
- expected unanswerable handled;
- average latency;
- median latency.

## Template tabel

| Metrica | Valoare |
| --- | ---: |
| Total intrebari |  |
| Top-1 URL match |  |
| Top-3 URL match |  |
| Confidence low |  |
| Intrebari fara raspuns sigur tratate corect |  |
| Latenta medie |  |
| Latenta mediana |  |
