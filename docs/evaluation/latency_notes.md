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

### Snapshot local in loc de live verification

Backendul nu mai refetch-uieste pagini oficiale la runtime pentru fiecare intrebare. Raspunsurile folosesc snapshotul local JSON/Qdrant, iar prospetimea este asigurata prin rebuild de index.

Configuratia curenta este:

```env
LIVE_VERIFY_ENABLED=false
LIVE_VERIFY_LIMIT=0
```

Aceasta elimina latenta introdusa de fetch-uri live, in special pentru PDF/DOCX, si face demo-ul mai predictibil. Daca site-urile oficiale se schimba, indexul trebuie reconstruit.

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
- Reconstruieste indexul inainte de evaluari sau demo-uri importante.
- Foloseste raspuns determinist pentru intrebari de navigare cand sursa este clara.
- Pastreaza contextul trimis catre Ollama compact si bazat pe cele mai bune fragmente oficiale.

## Limitari

Latenta masurata local nu este universala. Acelasi cod poate avea timpi diferiti pe alt calculator, cu alt model Ollama sau cu alta stare a indexului. De aceea, rezultatele de evaluare trebuie raportate impreuna cu modelul folosit, modul de rulare Qdrant si versiunea snapshotului local.
