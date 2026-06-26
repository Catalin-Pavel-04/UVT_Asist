# Interpretarea evaluarii independente Q&A 1000

## Rezumat global

Evaluarea independenta Q&A pe 1000 de intrebari a fost rulata pe stackul local UVT_Asist, prin endpointul `POST /chat`, folosind datasetul `backend/evaluation/eval_qa_1000_independent.json`.

Rezultatul global a fost:

| Metrica | Valoare |
| --- | ---: |
| Total intrebari | 1000 |
| Passed | 644 |
| Failed | 356 |
| Pass rate | 64.4% |
| Scor mediu | 72.34 |
| Scor median | 82.35 |
| Top-1 URL match | 439/694 (63.26%) |
| Top-3 URL match | 502/694 (72.33%) |
| Confidence match | 843/1000 (84.30%) |
| Erori | 0 |

Raportul complet este disponibil in [qa1000_independent_report.md](qa1000_independent_report.md), iar tabelele LaTeX sunt in [qa1000_independent_latex_tables.tex](qa1000_independent_latex_tables.tex).

## Interpretarea rezultatului de 64.4%

Un pass rate de 64.4% inseamna ca 644 din cele 1000 de cazuri au depasit pragul de scor stabilit de evaluator. Rezultatul indica o performanta functionala, dar neuniforma: sistemul raspunde bine pentru mai multe intentii administrative clare, insa are dificultati vizibile pe intrebari vagi, intrebari fara raspuns sigur si unele cazuri care cer surse metodologice sau calendaristice foarte precise.

Scorul mediu de 72.34 si scorul median de 82.35 arata ca raspunsul tipic este mai bun decat media. Diferenta dintre medie si mediana sugereaza existenta unui numar semnificativ de cazuri cu scor mic care trag media in jos. Din acest motiv, rezultatul global trebuie citit impreuna cu analiza pe categorii, nu ca o singura masura absoluta.

Faptul ca au existat 0 erori indica stabilitate tehnica in rularea evaluarii: backendul a returnat raspunsuri pentru toate cele 1000 de intrebari. Aceasta nu inseamna ca toate raspunsurile au fost corecte, ci doar ca fluxul aplicatiei nu a esuat la nivel de request.

## Categorii forte

Cele mai bune rezultate apar in categorii unde intrebarea are de obicei intentie clara si surse oficiale bine delimitate:

| Categorie | Pass rate | Interpretare |
| --- | ---: | --- |
| voluntariat_credite | 95% | Sistemul identifica foarte bine sursele si raspunsurile despre creditele de voluntariat. |
| contact_secretariat | 92% | Intrebarile de contact/secretariat sunt bine acoperite, mai ales cand exista pagini de contact clare. |
| cazare_camine | 87% | Raspunsurile despre cazare si camine au acuratete ridicata pe setul evaluat. |
| admitere | 80% | Intrebarile despre admitere sunt gestionate bine, desi nu perfect, probabil din cauza varietatii paginilor si documentelor oficiale. |

Aceste categorii sustin concluzia ca sistemul este potrivit pentru intrebari administrative concrete, cu intent clar si cu surse oficiale indexate.

## Categorii slabe

Categoriile slabe nu trebuie ascunse, deoarece arata limitele reale ale sistemului:

| Categorie | Pass rate | Interpretare |
| --- | ---: | --- |
| intrebari_vagi_ambigue | 16% | Sistemul gestioneaza slab intrebarile prea generale sau ambigue, unde ar trebui sa ceara clarificari mai des si mai explicit. |
| calendar_academic | 39% | Calendarul academic cere surse si date foarte specifice; scorul arata probleme de selectie a sursei sau de raspuns prudent cand dovada lipseste. |
| intrebari_fara_raspuns_sigur | 43% | Sistemul nu refuza suficient de constant intrebarile fara dovezi oficiale sau cu caracter predictiv/personal. |
| regulamente_metodologii | 59% | Intrebarile despre reguli si metodologii sunt mai dificile deoarece necesita documente oficiale exacte si selectie buna intre surse similare. |

Aceste rezultate indica directii de imbunatatire: clarificare pentru intrebari vagi, clasificare mai buna a intrebarilor fara raspuns sigur, si ranking mai strict pentru calendare, regulamente si metodologii.

## Interpretarea latentei

Latentele masurate au fost:

| Metrica | Secunde |
| --- | ---: |
| Medie | 23.323 |
| Mediana | 24.335 |
| P90 | 39.986 |
| P95 | 51.269 |

Latenta este ridicata pentru o experienta interactiva rapida, dar este coerenta cu un stack local care foloseste Ollama pentru analiza/generare si Qdrant pentru retrieval. Mediana de 24.335s arata ca timpul tipic de raspuns este de ordinul zecilor de secunde. P90 si P95 arata ca o parte importanta a cazurilor depaseste 40-50 de secunde, ceea ce trebuie mentionat ca limita operationala.

Rezultatul de latenta trebuie interpretat ca masuratoare in mediul local de test, nu ca performanta garantata pe alta masina. Timpul poate varia in functie de hardware, modelul Ollama, dimensiunea indexului, disponibilitatea Qdrant si complexitatea documentelor recuperate.

## Interpretarea generation_mode

Distributia `generation_mode` a fost:

| Generation mode | Numar |
| --- | ---: |
| ollama | 458 |
| local_source_navigation | 347 |
| fallback_ollama_error | 105 |
| none | 61 |
| clarification | 29 |

`ollama` arata cazurile in care raspunsul a fost generat cu modelul local. `local_source_navigation` arata ca o parte mare din intrebari au putut fi rezolvate determinist, prin directionarea catre sursa oficiala relevanta, fara sinteza extinsa. Acest comportament este potrivit pentru intrebari de tip orar, contact, admitere sau navigare catre pagina oficiala.

`fallback_ollama_error` apare in 105 cazuri si trebuie tratat ca semnal de robustete partiala: sistemul a avut un fallback cand generarea locala nu a mers, dar aceste cazuri trebuie analizate manual pentru a verifica daca raspunsurile raman utile si corecte. `none` si `clarification` indica situatii in care sistemul nu a produs o generatie standard, de obicei pentru clarificari, refuzuri sau cazuri in care raspunsul direct nu era sustinut.

## Interpretarea retrieval_backend

Distributia `retrieval_backend` a fost:

| Retrieval backend | Numar |
| --- | ---: |
| qdrant | 910 |
| clarification | 58 |
| unsupported_guard | 32 |

Faptul ca `qdrant` apare in 910 cazuri confirma ca evaluarea a folosit in principal fluxul local de retrieval vectorial. `clarification` si `unsupported_guard` arata ca exista si cazuri in care sistemul evita retrievalul standard si intra pe ramuri de clarificare sau refuz controlat. Acest lucru este dorit pentru intrebari ambigue sau nesustinute, dar scorurile slabe la `intrebari_vagi_ambigue` si `intrebari_fara_raspuns_sigur` arata ca aceste ramuri nu sunt inca aplicate suficient de bine.

## Limitele evaluatorului automat

Evaluatorul automat este util pentru comparatie reproductibila, dar nu inlocuieste o evaluare umana completa.

Limitele principale sunt:

- scorul foloseste rubrici si semnale observabile, nu judecata semantica umana completa;
- `ideal_answer` este o rubrica, nu un raspuns unic, deci overlapul lexical este doar informativ;
- Top-1 si Top-3 URL sunt stricte si depind de fragmentele definite in dataset;
- intrebarile fara URL asteptat masoara mai mult confidence, prudenta si comportamentul de clarificare/refuz;
- rezultatele depind de starea indexului local, de modelele Ollama configurate si de disponibilitatea Qdrant;
- latentele sunt dependente de mediul local de rulare;
- un raspuns poate primi scor mic chiar daca este partial util, sau scor mai bun decat merita daca bifeaza semnale automate fara sa fie ideal pentru utilizator.

## Analiza manuala recomandata

Cele 356 de esecuri trebuie analizate manual pe categorii, in special:

- `intrebari_vagi_ambigue`, pentru a vedea cand sistemul ar trebui sa ceara clarificari;
- `calendar_academic`, pentru a identifica probleme de sursa sau lipsa informatiei in index;
- `intrebari_fara_raspuns_sigur`, pentru a verifica daca raspunsurile sunt prea increzatoare;
- `regulamente_metodologii`, pentru a vedea daca rankingul prefera documentul oficial potrivit.

Analiza manuala ar trebui sa separe erorile de retrieval, erorile de confidence, erorile de formulare si cazurile in care datasetul cere o sursa foarte stricta. Aceasta analiza este necesara inainte de a decide modificari viitoare ale aplicatiei.

## Precizari metodologice

Rezultatul de 64.4% este valabil pe setul definit de 1000 de intrebari si pe configuratia locala folosita la rulare. Nu este o garantie universala pentru orice intrebare pe care un student ar putea sa o adreseze.

Benchmarkul nu a fost folosit pentru tuningul aplicatiei. El este folosit pentru evaluare finala si raportare, iar modificarile viitoare trebuie raportate separat daca schimba datasetul, criteriile de scoring, indexul, modelele sau logica de retrieval/generare.
