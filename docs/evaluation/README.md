# Rezultatele evaluării RAG

Rezultatele brute generate local rămân în `backend/data/evaluation/` și sunt ignorate de Git. Pentru lucrarea de licență, copiază manual sumarul Markdown relevant sau valorile finale într-un tabel din document.

Comanda completă recomandată:

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

Pentru comparația Q&A cu 100 de întrebări și răspunsuri ideale:

```powershell
python backend/scripts/evaluate_qa.py
```

Dataset-ul folosit este `backend/evaluation/eval_qa_100.json`. Scorul Q&A combină potrivirea surselor, confidence-ul, acoperirea termenilor esențiali din răspunsul ideal și tratarea întrebărilor fără răspuns sigur.

Metrici recomandate pentru raportare:

- total questions;
- top-1 URL match;
- top-3 URL match;
- low confidence count;
- expected unanswerable handled;
- average latency;
- median latency.

## Template tabel

| Metrică | Valoare |
| --- | ---: |
| Total întrebări |  |
| Top-1 URL match |  |
| Top-3 URL match |  |
| Confidence low |  |
| Întrebări fără răspuns sigur tratate corect |  |
| Latență medie |  |
| Latență mediană |  |
