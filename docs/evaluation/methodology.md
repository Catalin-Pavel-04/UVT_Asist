# Metodologie de evaluare RAG

Evaluarea proiectului UVT_Asist foloseste un set definit in repository, cu 100 de intrebari romanesti reprezentative pentru scenarii studentesti. Setul este versionat in `backend/evaluation/eval_questions.json`.

Scopul evaluarii este masurarea comportamentului sistemului pe intrebari cunoscute, relevante pentru demo si pentru lucrarea de licenta. Rezultatele nu reprezinta o garantie generala absoluta pentru orice intrebare posibila.

## Setul de 100 de intrebari

Intrebarile acopera categorii administrative si educationale uzuale:

- orar;
- contact si secretariat;
- admitere;
- burse;
- regulamente si metodologii;
- cazare si camine;
- calendar academic;
- credite de voluntariat;
- intrebari vagi;
- intrebari fara raspuns sigur in sursele oficiale.

Fiecare intrebare poate include asteptari despre intentie, surse oficiale probabile, comportament de confidence si daca sistemul ar trebui sau nu sa ofere un raspuns direct.

Setul nu trebuie modificat pentru a imbunatati artificial rezultatele. Orice schimbare a datasetului trebuie tratata ca schimbare metodologica, nu ca simpla optimizare de cod.

## Metrici

### Rata de trecere

Rata de trecere masoara procentul intrebarilor evaluate care satisfac criteriile asteptate. Un caz poate trece daca raspunsul este sustinut de sursele oficiale potrivite sau, pentru intrebarile fara raspuns sigur, daca sistemul refuza corect sa inventeze.

### Scor mediu Q&A

Scorul mediu Q&A agrega calitatea raspunsului pe setul evaluat. El reflecta atat calitatea surselor selectate, cat si conformitatea raspunsului cu asteptarile definite in evaluare.

### Top-1 URL corect

Top-1 URL corect verifica daca prima sursa returnata de backend corespunde unei surse oficiale asteptate pentru intrebare. Este o metrica stricta, importanta pentru intrebari unde exista o pagina oficiala evidenta, cum ar fi orar sau contact.

### Top-3 URL corect

Top-3 URL corect verifica daca una dintre primele trei surse returnate este o sursa asteptata. Aceasta metrica este utila cand mai multe pagini oficiale pot fi relevante pentru aceeasi intrebare.

### Potrivire nivel incredere

Potrivirea nivelului de incredere verifica daca `confidence` si `confidence_score` sunt coerente cu dificultatea cazului. Intrebarile cu dovezi clare ar trebui sa aiba confidence mai ridicat, iar intrebarile vagi, personale, predictive sau nesustinute de surse oficiale ar trebui sa fie marcate cu confidence scazut.

### Latenta medie si mediana

Latenta masoara durata apelurilor `/chat`. Media poate fi influentata de cazuri lente, cum ar fi documente PDF, live verification sau generarea Ollama. Mediana arata comportamentul tipic pentru majoritatea intrebarilor.

## Interpretarea rezultatelor

Evaluarea trebuie citita ca o verificare reproductibila pe setul definit in proiect. Un scor bun pe cele 100 de intrebari indica faptul ca sistemul gestioneaza bine scenariile alese, dar nu demonstreaza ca toate intrebarile posibile vor primi raspuns corect.

Pentru intrebari noi, calitatea depinde de:

- existenta informatiilor in sursele oficiale indexate;
- prospetimea indexului;
- disponibilitatea Ollama si Qdrant;
- calitatea extragerii textului din pagini sau documente;
- claritatea intrebarii studentului.

## Legatura cu raportul comparativ

Raportul comparativ existent este:

[qa_before_after_stats.md](qa_before_after_stats.md)

Acesta compara rezultatele inainte si dupa optimizari pentru acelasi set de 100 de intrebari. Raportul include rata de trecere, scorul mediu Q&A, potrivirea URL-urilor top-1/top-3, potrivirea nivelului de incredere si latenta.

In lucrarea de licenta, raportul poate fi folosit pentru a sustine efectul refinarilor de retrieval, reranking determinist, tratarea intrebarilor vagi si refuzul intrebarilor fara dovezi oficiale suficiente.
