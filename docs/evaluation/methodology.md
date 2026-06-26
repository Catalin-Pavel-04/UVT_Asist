# Metodologie de evaluare RAG

Evaluarea proiectului UVT_Asist foloseste doua seturi versionate in repository:

- `backend/evaluation/eval_questions.json`: setul de evaluare RAG prin `backend/scripts/evaluate_rag.py`, cu 41 de intrebari orientate spre verificarea surselor, Top-1/Top-3 URL, confidence si latenta.
- `backend/evaluation/eval_qa_100.json`: setul Q&A de 100 de intrebari prin `backend/scripts/evaluate_qa.py`, folosit pentru scorul mediu Q&A si raportul comparativ `qa_before_after_stats.md`.
- `backend/data/evaluation/eval_qa_1000_independent.json`: set independent de 1000 de intrebari pentru evaluarea finala Q&A. Datasetul este plasat local in zona de evaluare si este evaluat prin `backend/scripts/evaluate_qa_1000_independent.py`.

Aceasta separare este importanta pentru raportarea academica: primul set masoara in principal recuperarea surselor oficiale si comportamentul de siguranta, iar al doilea combina surse, raspuns, confidence si acoperire semantica intr-un scor 0-100.

Rezultatele nu reprezinta o garantie generala absoluta pentru orice intrebare posibila. Ele masoara comportamentul sistemului pe seturile definite in proiect, in conditiile locale in care ruleaza Flask, Ollama si Qdrant.

## Gruparea intrebarilor pe categorii

Intrebarile sunt grupate dupa intentia administrativa sau academica pe care sistemul trebuie sa o detecteze si sa o rezolve cu surse oficiale:

- `orar`: intrebari despre orare, inclusiv variante informale sau cu typo.
- `contact/secretariat`: pagini de contact, secretariat si date administrative.
- `admitere`: pagini oficiale despre procesul de admitere, taxe si aplicare.
- `burse`: metodologii, regulamente si pagini despre burse.
- `regulamente/metodologii`: reguli academice, metodologii si documente institutionale.
- `cazare/camine`: cazare, camine, taxe si reguli de cazare.
- `calendar academic`: perioade de semestru, sesiune, vacanta si calendar universitar.
- `voluntariat/credite`: credite pentru voluntariat, portofoliu si depunere documente.
- `intrebari vagi`: intrebari prea generale, unde un raspuns specific ar fi riscant.
- `intrebari fara raspuns sigur in sursele oficiale`: intrebari predictive, personale sau administrative care nu pot fi confirmate din sursele publice indexate.

Gruparea permite analiza pe tipuri de esec: de exemplu, un sistem poate fi bun la intrebari despre admitere, dar slab la intrebari vagi sau la refuzul intrebarilor fara dovezi oficiale.

## Rularea evaluarii RAG

Evaluarea RAG trimite fiecare intrebare catre endpointul public `POST /chat`, cu `faculty_id` din dataset si `history=[]`.

```powershell
python backend\scripts\evaluate_rag.py
```

Filtre utile:

```powershell
python backend\scripts\evaluate_rag.py --category burse
python backend\scripts\evaluate_rag.py --limit 5
python backend\scripts\evaluate_rag.py --backend-url http://127.0.0.1:5000 --timeout 180
```

Scriptul verifica mai intai `GET /health`. Daca backendul nu raspunde, evaluarea se opreste si nu produce un rezultat fals pozitiv.

Pentru fiecare intrebare, evaluatorul salveaza raspunsul, sursele, metadata de confidence, backendul de retrieval, modul de generare, flagul compatibil `live_verified` si timpul de raspuns. In configuratia curenta, `live_verified=false`, deoarece raspunsurile folosesc snapshotul local JSON/Qdrant. Rapoartele generate local sunt scrise in `backend/data/evaluation/`.

## Rularea evaluarii Q&A 100

Evaluarea Q&A ruleaza pe setul de 100 de intrebari si compara raspunsul generat cu o rubrica definita in dataset.

```powershell
python backend\scripts\evaluate_qa.py
```

Acest script produce `qa_score`, `passed`, `confidence_match`, `top1_url_match`, `top3_url_match`, acoperire de fraze obligatorii, acoperire de termeni din raspunsul ideal si latenta. Raportul comparativ existent este:

[qa_before_after_stats.md](qa_before_after_stats.md)

## Evaluare independenta Q&A pe 1000 de intrebari

Evaluarea independenta Q&A pe 1000 de intrebari este folosita ca evaluare finala pentru colectarea rezultatelor din documentatie si din lucrarea de licenta. Ea nu este un mecanism de tuning si nu trebuie folosita pentru a modifica intrebarile, rubricile sau logica aplicatiei ca sa imbunatateasca artificial scorurile.

Datasetul contine 1000 de intrebari impartite in 10 categorii, cu cate 100 de intrebari per categorie. Intrebarile sunt independente si generate in afara Codex. Fiecare item contine intrebarea, facultatea, `ideal_answer`, `should_have_answer`, tipul raspunsului, intentul asteptat, tipul de pagina asteptat, fragmente de URL asteptate, confidence asteptat, termeni obligatorii si termeni interzisi.

`ideal_answer` este tratat ca rubrica, nu ca raspuns unic. Nu se face comparatie exacta text-la-text, deoarece un raspuns corect poate fi formulat in mai multe moduri. Scoringul favorizeaza raspunsurile care folosesc surse oficiale corecte, au confidence potrivit, acopera `required_terms`, evita `forbidden_terms` si trateaza prudent intrebarile fara raspuns sigur.

Rularea se face doar cu stackul local pornit:

```powershell
ollama serve
docker compose up -d qdrant
python backend/app.py
```

Test rapid:

```powershell
python backend/scripts/evaluate_qa_1000_independent.py --limit 10
```

Rulare completa cu resume:

```powershell
python backend/scripts/evaluate_qa_1000_independent.py --dataset backend/evaluation/eval_qa_1000_independent.json --backend-url http://127.0.0.1:5000 --timeout 180 --delay-ms 150 --run-label final_1000 --resume
```

Generarea raportului curat pentru documentatie si a tabelelor LaTeX:

```powershell
python backend/scripts/report_qa_1000_independent.py --input backend/data/evaluation/<result_file>.json
```

Metricile raportate includ:

- `pass_rate`: procentul de intrebari cu scor cel putin 70;
- `average_score`: scorul mediu pe toate intrebarile evaluate;
- `median_score`: scorul median;
- `ideal_overlap_score`: overlap lexical informativ intre raspuns si `ideal_answer`, fara rol de scor principal;
- `top1_url_match`: prima sursa contine un fragment asteptat;
- `top3_url_match`: una dintre primele trei surse contine un fragment asteptat;
- `confidence_match`: nivelul de confidence este in lista asteptata;
- `expected_unanswerable_handled`: intrebarile fara raspuns sigur sunt tratate prudent;
- latenta medie, mediana, p90 si p95.

## Interpretarea rezultatelor Q&A 1000

Rularea finala pe setul independent Q&A 1000 a produs 644 de cazuri `passed` si 356 de cazuri `failed`, adica un pass rate de 64.4%. Scorul mediu a fost 72.34, iar scorul median 82.35. Diferenta dintre medie si mediana arata ca raspunsul tipic este mai bun decat media, dar exista categorii si cazuri cu scoruri mici care trag rezultatul global in jos.

Metricile de sursa arata ca Top-1 URL match a fost 439/694 (63.26%), iar Top-3 URL match a fost 502/694 (72.33%). Confidence match a fost 843/1000 (84.30%), iar evaluarea nu a inregistrat erori de request sau executie. Aceste cifre sustin o concluzie prudenta: sistemul este functional si stabil pe setul evaluat, dar acuratetea nu este uniforma pe toate tipurile de intrebari.

Cele mai bune categorii au fost `voluntariat_credite` (95%), `contact_secretariat` (92%), `cazare_camine` (87%) si `admitere` (80%). Acestea sunt categorii cu intentii administrative relativ clare si surse oficiale bine delimitate. Cele mai slabe categorii au fost `intrebari_vagi_ambigue` (16%), `calendar_academic` (39%), `intrebari_fara_raspuns_sigur` (43%) si `regulamente_metodologii` (59%). Aceste rezultate arata limitele sistemului in clarificarea intrebarilor vagi, in refuzul intrebarilor fara dovezi oficiale si in selectia surselor foarte specifice pentru calendare, regulamente si metodologii.

Latenta medie a fost 23.323s, mediana 24.335s, P90 39.986s si P95 51.269s. Aceste valori sunt specifice mediului local de rulare si trebuie raportate ca limita operationala: sistemul poate raspunde corect, dar timpul de raspuns este de ordinul zecilor de secunde pentru multe intrebari.

Distributia `generation_mode` a fost: `ollama` 458, `local_source_navigation` 347, `fallback_ollama_error` 105, `none` 61 si `clarification` 29. Distributia `retrieval_backend` a fost: `qdrant` 910, `clarification` 58 si `unsupported_guard` 32. Acest lucru confirma ca evaluarea a folosit in principal retrievalul local prin Qdrant, cu ramuri de clarificare sau refuz controlat pentru o parte din cazuri.

Interpretarea completa se afla in [qa1000_interpretation.md](qa1000_interpretation.md), iar raportul numeric complet in [qa1000_independent_report.md](qa1000_independent_report.md). Rezultatul trebuie folosit ca evaluare pe setul definit, nu ca garantie universala, iar benchmarkul nu a fost folosit pentru tuningul aplicatiei.

Rezultatele sunt valabile pe setul definit si pe configuratia locala folosita la rulare, nu reprezinta garantie universala pentru orice intrebare posibila.

## Ce inseamna pass/fail

In evaluarea Q&A, fiecare intrebare primeste un `qa_score` intre 0 si 100. Cazul este marcat `passed=true` daca scorul este cel putin 70.

Pentru intrebarile care trebuie sa aiba raspuns (`should_have_answer=true`), scorul combina:

- pana la 30 de puncte pentru sursa corecta: 30 daca Top-1 URL este corect, 18 daca doar Top-3 contine URL corect, 0 daca sursa asteptata lipseste;
- pana la 30 de puncte pentru acoperirea frazelor obligatorii din rubrica;
- pana la 20 de puncte pentru acoperirea termenilor relevanti din raspunsul ideal;
- 10 puncte pentru potrivirea nivelului asteptat de confidence;
- 10 puncte daca raspunsul nu contine fraze interzise sau afirmatii nepotrivite.

Pentru intrebarile fara raspuns sigur (`should_have_answer=false`), pass/fail nu cere inventarea unui raspuns. Scorul recompenseaza comportamentul prudent:

- 45 de puncte daca sistemul semnaleaza dovezi insuficiente, `confidence=low`, `evidence.answerable=false` sau lipsa surselor utile;
- 25 de puncte pentru acoperirea partiala a mesajului de refuz/clarificare asteptat;
- 20 de puncte pentru potrivirea confidence-ului asteptat;
- 10 puncte daca nu apar fraze interzise sau informatii fabricate.

In evaluarea RAG simpla, `evaluate_rag.py` nu calculeaza un `passed` global. El raporteaza metrici directe: raspuns primit, confidence low, Top-1 URL, Top-3 URL, intrebari fara raspuns sigur tratate corect si latenta.

## Cum se calculeaza scorul mediu

Scorul mediu Q&A este media aritmetica a tuturor valorilor `qa_score` produse de `evaluate_qa.py`:

```text
scor_mediu = suma(qa_score pentru toate intrebarile) / numar_intrebari
```

Scorul median este mediana acelorasi valori. Media este utila pentru comparatii globale, iar mediana arata comportamentul tipic cand exista cateva cazuri foarte slabe sau foarte lente.

## Top-1 URL corect

`Top-1 URL corect` inseamna ca prima sursa returnata de backend contine unul dintre fragmentele definite in `expected_url_contains` pentru intrebarea respectiva.

Exemplu: pentru o intrebare despre orarul de la Informatica, datasetul poate cere ca URL-ul sa contina `info.uvt.ro/orare`. Daca prima sursa returnata contine acest fragment, `top1_url_match=true`.

Aceasta este o metrica stricta. Ea verifica daca sistemul pune cea mai relevanta sursa oficiala pe primul loc, nu doar daca sursa apare undeva in lista.

## Top-3 URL corect

`Top-3 URL corect` inseamna ca cel putin una dintre primele trei surse returnate contine unul dintre fragmentele asteptate din `expected_url_contains`.

Aceasta metrica este mai permisiva decat Top-1 si este utila pentru intrebari unde exista mai multe pagini oficiale acceptabile: de exemplu, o pagina UVT generala si o pagina de facultate pot fi ambele corecte pentru unele intrebari.

Daca o intrebare nu are fragmente asteptate de URL, evaluarea Q&A trateaza Top-1/Top-3 ca indeplinite, pentru ca acel caz masoara mai degraba refuzul, clarificarea sau confidence-ul decat potrivirea unei pagini exacte.

## Cum este masurata latenta

Latenta este masurata in jurul fiecarui apel `POST /chat`, folosind `time.perf_counter()` in scripturile de evaluare.

Intervalul include:

- trimiterea requestului catre backend;
- analiza intrebarii;
- embedding local prin Ollama, daca este folosit;
- cautarea in Qdrant sau fallbackul local;
- reranking determinist;
- accesul la snapshotul local JSON/Qdrant;
- generarea raspunsului cu Ollama;
- serializarea raspunsului JSON.

Evaluatorul raporteaza latenta per intrebare, latenta medie si latenta mediana. Media poate creste din cauza unor cazuri lente cu documente mari, PDF-uri din index sau generare Ollama. Mediana este mai reprezentativa pentru experienta tipica.

## De ce intrebarile fara raspuns sigur sunt evaluate separat

Un asistent universitar bazat pe RAG nu trebuie sa maximizeze doar numarul de raspunsuri directe. Pentru intrebari predictive, personale sau nesustinute de surse oficiale, comportamentul corect este sa refuze un raspuns sigur, sa explice lipsa dovezilor sau sa ceara clarificari.

Exemple:

- media minima de admitere de anul viitor;
- nota personala la un examen;
- bursa pe care o va primi un student anume;
- absenta viitoare a unui profesor, daca nu exista anunt oficial.

Aceste cazuri sunt evaluate separat deoarece o formulare fluenta poate fi gresita si periculoasa academic. Sistemul este recompensat pentru `confidence=low`, `evidence.answerable=false`, lipsa surselor utile sau raspunsuri care explica explicit ca sursele oficiale nu sustin o concluzie.

## Interpretarea rezultatelor

Rezultatele trebuie citite ca o verificare reproductibila pe seturile definite in proiect, nu ca o certificare generala a corectitudinii.

Calitatea pentru intrebari noi depinde de:

- existenta informatiei in sursele oficiale indexate;
- prospetimea indexului;
- disponibilitatea Ollama si Qdrant;
- calitatea extragerii textului din HTML, PDF sau documente;
- claritatea intrebarii;
- versiunea snapshotului local si cache-urile locale.

Seturile de evaluare nu trebuie modificate pentru a imbunatati artificial rezultatele. Orice schimbare de dataset trebuie raportata ca schimbare metodologica.
