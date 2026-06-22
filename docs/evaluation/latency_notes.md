# Note despre latenta

Latenta UVT_Asist depinde de etapa RAG parcursa pentru fiecare intrebare. Sistemul ruleaza local, deci performanta este influentata de hardware, de modelul Ollama, de dimensiunea indexului si de disponibilitatea Qdrant.

## Surse principale de latenta

### Embeddings pentru query

Fiecare intrebare are nevoie de cel putin un embedding local. Pentru unele tipuri de intrebari, backendul construieste query-uri suplimentare tintite, de exemplu pentru calendar academic, contact central sau documente de bursa sociala.

Acest pas depinde de modelul de embedding si de timpul de raspuns Ollama.

### Cautare Qdrant

Cautarea vectoriala este in general rapida, dar latenta poate creste daca:

- colectia este foarte mare;
- se fac mai multe treceri de cautare cu filtre diferite;
- Qdrant ruleaza pe un disc lent sau intr-un container incarcat.

### Reranking determinist

Reranking-ul ruleaza in Python si foloseste semnale lexicale, de URL, de titlu, de facultate si de tip de pagina. Costul este de obicei mic fata de embeddings si generare, dar poate creste cand fallback-ul lexical scaneaza un index JSON foarte mare.

Pentru indexuri mari, runtime-ul trebuie sa ramana Qdrant-first.

### Live verification

Live verification poate adauga latenta deoarece backendul refetch-uieste un numar mic de pagini oficiale. Documentele PDF sau DOCX sunt mai lente decat paginile HTML.

Pentru demo offline sau evaluari strict reproductibile, live verification poate fi dezactivata:

```env
LIVE_VERIFY_ENABLED=false
LIVE_VERIFY_LIMIT=0
```

### Generare cu Ollama

Generarea raspunsului este de obicei cea mai variabila etapa. Latenta depinde de:

- modelul de generare;
- CPU/GPU disponibil;
- lungimea contextului trimis;
- lungimea raspunsului cerut;
- temperatura si limitele `num_predict`.

Pentru intrebari simple de navigare, backendul poate returna un raspuns local determinist, evitand generarea.

## Media vs mediana

In rapoarte, latenta medie si mediana trebuie interpretate impreuna:

- mediana arata comportamentul tipic;
- media este sensibila la cazuri lente;
- diferenta mare intre medie si mediana sugereaza ca exista cateva intrebari costisitoare, de obicei legate de documente sau generare.

Raportul comparativ existent arata aceasta diferenta:

[qa_before_after_stats.md](qa_before_after_stats.md)

## Practici pentru reducerea latentei

- Pastreaza Qdrant disponibil si indexul vectorial complet.
- Reconstruieste indexul vectorial dupa schimbarea modelului de embedding.
- Evita fallback-ul lexical complet pe indexuri foarte mari.
- Limiteaza live verification la putine URL-uri.
- Foloseste raspuns determinist pentru intrebari de navigare cand sursa este clara.
- Pastreaza contextul trimis catre Ollama compact si bazat pe cele mai bune fragmente oficiale.

## Limitari

Latenta masurata local nu este universala. Acelasi cod poate avea timpi diferiti pe alt calculator, cu alt model Ollama sau cu alta stare a indexului. De aceea, rezultatele de evaluare trebuie raportate impreuna cu modelul folosit, modul de rulare Qdrant si starea live verification.
