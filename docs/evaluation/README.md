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
