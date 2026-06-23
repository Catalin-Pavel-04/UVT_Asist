# Plan de ablation study

Acest document descrie cum poate fi evaluata contributia fiecarei componente majore din pipeline-ul UVT_Asist. Scopul nu este sa schimbe rezultatele existente, ci sa defineasca o metoda reproductibila pentru o analiza academica ulterioara.

Un ablation study compara mai multe variante ale aceluiasi sistem, pastrand acelasi set de intrebari, aceeasi versiune de index si acelasi mediu local. Diferenta dintre rezultate arata contributia probabila a componentelor eliminate sau adaugate.

## Conditii comune

Pentru o comparatie corecta, toate variantele trebuie rulate cu:

- acelasi `backend/evaluation/eval_questions.json` pentru metrici RAG;
- acelasi `backend/evaluation/eval_qa_100.json` pentru scor Q&A;
- acelasi snapshot `backend/data/page_index.json`;
- aceeasi colectie Qdrant sau aceeasi reconstruire vectoriala;
- aceleasi modele Ollama pentru generare si embedding;
- acelasi backend URL si aceleasi timeout-uri;
- aceeasi stare a live verification cache-ului, ideal golit inainte de fiecare runda;
- acelasi hardware local, pe cat posibil.

Comenzi de baza:

```powershell
python backend\scripts\evaluate_rag.py
python backend\scripts\evaluate_qa.py
```

Rezultatele generate se salveaza in `backend/data/evaluation/`. Pentru raportare, se compara JSON/CSV/Markdown generate pentru fiecare varianta.

## Variante propuse

### 1. Lexical only

Descriere: sistemul foloseste doar indexul local JSON si ranking lexical/determinist, fara cautare vectoriala Qdrant.

Cum ar fi rulat:

- se dezactiveaza temporar cautarea vectoriala sau se forteaza fallbackul lexical intr-o ramura experimentala;
- se pastreaza aceleasi surse si acelasi `page_index.json`;
- se ruleaza `evaluate_rag.py` si `evaluate_qa.py`.

Ce ar demonstra:

- cat de mult poate acoperi sistemul doar prin potrivire de termeni;
- unde esueaza intrebarile parafrazate, cu typo sau formulate indirect;
- daca rankingul lexical favorizeaza prea des pagini generale.

Metrici asteptate relevante:

- scadere Top-1/Top-3 pentru intrebari parafrazate;
- scor Q&A mai mic la categorii cu terminologie variata;
- latenta potential mai mica, dar calitate mai slaba.

### 2. Vector only

Descriere: sistemul foloseste cautarea semantica Qdrant, dar fara reranking determinist suplimentar.

Cum ar fi rulat:

- intr-o ramura experimentala, rezultatele Qdrant sunt folosite aproape direct;
- se evita boosturile pentru facultate, tip pagina, policy, titlu, URL si termeni lexicali;
- se ruleaza aceleasi evaluari.

Ce ar demonstra:

- cat de buna este recuperarea semantica pura;
- daca embeddings gasesc pagini relevante chiar atunci cand termenii exacti difera;
- unde cautarea vectoriala aduce pagini semantic apropiate, dar administrative gresite.

Metrici asteptate relevante:

- Top-3 poate ramane rezonabil;
- Top-1 poate scadea daca pagina specifica nu este promovata peste pagini generale;
- cazurile de regulamente si burse pot fi mai instabile fara semnale de policy.

### 3. Vector + reranking

Descriere: sistemul foloseste Qdrant pentru candidati si reranking determinist pentru a promova surse oficiale specifice.

Cum ar fi rulat:

- se foloseste pipeline-ul semantic + reranking;
- live verification este dezactivata pentru a izola efectul rerankingului;
- se ruleaza evaluarea pe aceleasi seturi.

Ce ar demonstra:

- contributia regulilor deterministe peste cautarea semantica;
- imbunatatirea Top-1 fata de `vector only`;
- efectul semnalelor de facultate, tip pagina, titlu, URL si policy.

Metrici asteptate relevante:

- crestere Top-1 URL corect;
- imbunatatire in categorii cu pagini oficiale specifice: orar, contact, calendar, burse;
- latenta apropiata de vector only, deoarece rerankingul este local si determinist.

### 4. Vector + reranking + live verification

Descriere: sistemul foloseste Qdrant, reranking si verificarea live a surselor de top, dar fara alte optimizari de raspuns din sistemul complet, daca acestea sunt izolate intr-o ramura experimentala.

Cum ar fi rulat:

- se activeaza live verification pentru sursele selectate;
- se goleste cache-ul de live verification inainte de runda, apoi se noteaza separat rezultatele cu cache rece si cache cald;
- se ruleaza evaluarea.

Ce ar demonstra:

- daca verificarea live creste increderea in sursele selectate;
- impactul live verification asupra latentei;
- cazurile unde pagina oficiala s-a schimbat fata de indexul local.

Metrici asteptate relevante:

- crestere a numarului de surse verificate;
- posibila imbunatatire a confidence-ului;
- latenta medie mai mare la cache rece;
- latenta mai buna la cache cald.

### 5. Full system

Descriere: configuratia principala a aplicatiei: index local, Qdrant, reranking determinist, policy routing, live verification controlata, prompt RAG si generare locala cu Ollama.

Cum ar fi rulat:

```powershell
python backend\scripts\evaluate_rag.py
python backend\scripts\evaluate_qa.py
```

Ce ar demonstra:

- performanta sistemului final folosit in demo;
- capacitatea de a combina retrieval semantic, reguli deterministe, verificare surse si generare locala;
- comportamentul pe intrebari fara raspuns sigur.

Metrici asteptate relevante:

- cel mai bun echilibru intre Top-1/Top-3, scor Q&A si refuz controlat;
- latenta mai mare decat variantele simplificate, dar cu raspunsuri mai sigure;
- confidence mai coerent cu dificultatea intrebarii.

## Tabel recomandat pentru raport

| Varianta | Top-1 URL | Top-3 URL | Scor mediu Q&A | Pass rate | Confidence match | Unanswerable handled | Latenta medie | Latenta mediana |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Lexical only |  |  |  |  |  |  |  |  |
| Vector only |  |  |  |  |  |  |  |  |
| Vector + reranking |  |  |  |  |  |  |  |  |
| Vector + reranking + live verification |  |  |  |  |  |  |  |  |
| Full system |  |  |  |  |  |  |  |  |

## Interpretare academica

Un ablation study nu trebuie folosit pentru a alege manual intrebari favorabile. Toate variantele trebuie evaluate pe aceleasi seturi. Daca o varianta esueaza pe anumite categorii, acele esecuri trebuie raportate, deoarece ele arata de ce componentele adaugate sunt necesare.

In lucrare, concluzia asteptata ar trebui formulata prudent: imbunatatirile observate pe seturile locale sugereaza contributia componentelor respective, dar nu demonstreaza performanta universala pe orice intrebare sau pe orice versiune viitoare a site-urilor UVT.
