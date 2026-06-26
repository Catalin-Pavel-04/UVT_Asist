# Analiza esecurilor si limitari

Acest document grupeaza limitele observate in evaluari, cazurile in care sistemul trebuie sa ceara clarificari sau sa refuze un raspuns sigur si taxonomia recomandata pentru review manual.

## Limite masurate in Q&A 1000

Evaluarea independenta pe 1000 de intrebari a produs:

- pass rate global: 64.4%;
- Top-1 URL match: 439/694 (63.26%);
- Top-3 URL match: 502/694 (72.33%);
- confidence match: 843/1000 (84.30%);
- erori tehnice: 0.

Cele mai slabe categorii au fost:

- `intrebari_vagi_ambigue`: 16%;
- `calendar_academic`: 39%;
- `intrebari_fara_raspuns_sigur`: 43%;
- `regulamente_metodologii`: 59%.

Aceste categorii arata ca mecanismele de clarificare, refuz prudent si selectie a surselor foarte specifice trebuie imbunatatite.

## Limite de latenta

Latenta evaluarii Q&A 1000 a fost:

- medie: 23.323s;
- mediana: 24.335s;
- P90: 39.986s;
- P95: 51.269s.

Aceste valori sunt ridicate pentru o experienta conversationala rapida. Ele sunt specifice mediului local de test si depind de hardware, modelul Ollama, dimensiunea indexului, disponibilitatea Qdrant si complexitatea surselor recuperate.

## Fallback Ollama

`fallback_ollama_error` apare in 105 cazuri din evaluarea Q&A 1000. Acest lucru arata ca sistemul are o cale de fallback cand generarea locala nu reuseste, dar cazurile respective trebuie analizate manual pentru a verifica daca raspunsul ramas este suficient de util si corect.

## Limite de surse si index

Sistemul raspunde din snapshotul local JSON/Qdrant. Daca o informatie oficiala nu este indexata sau s-a schimbat dupa ultimul build, raspunsul poate fi incomplet sau invechit.

Indexul trebuie reconstruit cand:

- se schimba sursele oficiale;
- se schimba crawlerul sau chunking-ul;
- se schimba modelul de embedding;
- se pregateste un demo care necesita surse actuale.

## Limite ale evaluatorului automat

Evaluatorul Q&A 1000 nu inlocuieste analiza umana. El foloseste rubrici si semnale observabile, nu judecata semantica completa.

Riscuri ale evaluatorului:

- un raspuns partial util poate primi scor mic daca lipseste URL-ul strict asteptat;
- un raspuns poate bifa semnale automate fara sa fie ideal pentru student;
- intrebarile fara URL asteptat masoara mai mult prudenta si confidence decat selectia unei pagini exacte;
- rezultatele sunt valabile pe datasetul definit, nu pentru toate formularile posibile.

## Limite operationale

Aplicatia este proiectata pentru rulare locala, nu ca serviciu public expus pe internet. Pentru expunere publica ar fi necesare autentificare, rate limiting, hardening CORS, limite stricte de payload si audit suplimentar de logging.

OCR este optional si depinde de configurarea separata din `backend/requirements-ocr.txt` si `backend/scripts/setup_ocr_venv.ps1`.

## Cazuri unde sistemul trebuie sa ceara clarificari

Exemple:

- `Unde gasesc orarul?` fara facultate selectata sau mentionata, cand utilizatorul este in context UVT general.
- `Unde gasesc secretariatul?` fara facultate, cand nu este clar daca se cere contactul UVT central sau secretariatul unei facultati.
- `Am o problema cu facultatea, unde ma uit?`
- `Vreau informatii importante pentru mine.`
- `Ce trebuie sa fac ca student?`

Motivul este ca intrebarea este prea vaga sau depinde de facultate. Alegerea unei surse concrete fara clarificare ar putea duce la un raspuns gresit.

## Cazuri unde sistemul trebuie sa refuze un raspuns sigur

Exemple:

- `Ce bursa voi primi eu luna viitoare?`
- `Voi primi loc la camin anul acesta?`
- `Care va fi media minima de admitere anul viitor?`
- `Ce decizie va lua comisia pentru dosarul meu?`
- `Profesorul X va lipsi maine?`
- `Care este parola mea de StudentWeb?`
- `Poti garanta ca intru la buget?`

Motivul este ca raspunsul cere predictii, decizii personale, date private sau informatii care nu pot fi confirmate din sursele oficiale indexate.

## Cazuri unde sursele pot fi incomplete

Exemple:

- `Ce acte trebuie daca situatia mea familiala este foarte specifica?`
- `Unde obtin fiecare document justificativ pentru bursa sociala?`
- `Care este taxa exacta peste doi ani?`
- `Ce se intampla daca regulamentul a fost modificat ieri?`

Chiar daca sistemul gaseste o metodologie sau un regulament, unele detalii pot lipsi, pot depinde de situatia personala sau pot necesita confirmare administrativa directa.

## Comportament asteptat

Pentru cazurile de mai sus, comportamentul dorit este:

- confidence `low`;
- raspuns care explica limitarea;
- zero sau putine surse, doar daca sunt oficiale si relevante partial;
- fara reguli, termene sau decizii inventate;
- cerere de clarificare cand problema este facultatea, categoria sau contextul.

Acest comportament este parte din strategia de reducere a halucinatiilor si este inclus in evaluarea proiectului.

## Review manual pentru esecurile Q&A 1000

Evaluarea automata Q&A 1000 a produs 356 de cazuri `failed`. Aceste cazuri trebuie analizate manual inainte de a trage concluzii despre ce trebuie modificat in aplicatie.

Scopul review-ului manual este separarea tipurilor de esec:

- retrieval gresit;
- informatie lipsa din index;
- confidence nepotrivit;
- intrebare vaga care trebuia clarificata;
- intrebare fara raspuns sigur tratata prea increzator;
- caz in care evaluatorul automat este prea strict;
- ambiguitate in dataset;
- problema de latenta sau generare.

## Taxonomie recomandata

| Cod | Descriere |
| --- | --- |
| `retrieval_wrong_source` | Sistemul returneaza o sursa oficiala, dar nu sursa potrivita pentru intrebare. |
| `missing_source_in_index` | Sursa corecta nu pare sa fie prezenta in indexul local. |
| `confidence_miscalibrated` | Raspunsul este util, dar confidence-ul este prea mare sau prea mic fata de dovezi. |
| `vague_question_not_clarified` | Intrebarea este ambigua, dar sistemul raspunde direct in loc sa ceara clarificare. |
| `unsupported_question_answered_too_confidently` | Intrebarea nu are raspuns sigur in surse oficiale, dar sistemul raspunde prea sigur. |
| `evaluator_false_negative` | Raspunsul pare acceptabil manual, dar evaluatorul automat l-a marcat esec. |
| `dataset_ambiguous` | Rubrica sau asteptarea din dataset este ambigua sau prea stricta. |
| `latency_or_generation_issue` | Problema principala este timpul de raspuns, fallback-ul de generare sau o eroare a modelului local. |

## Tabel-template

| ID intrebare | Categorie | Scor automat | Cod esec | Sursa returnata | Evaluare manuala | Actiune recomandata |
| --- | --- | ---: | --- | --- | --- | --- |
|  |  |  | `retrieval_wrong_source` |  |  |  |
|  |  |  | `missing_source_in_index` |  |  |  |
|  |  |  | `confidence_miscalibrated` |  |  |  |
|  |  |  | `vague_question_not_clarified` |  |  |  |
|  |  |  | `unsupported_question_answered_too_confidently` |  |  |  |
|  |  |  | `evaluator_false_negative` |  |  |  |
|  |  |  | `dataset_ambiguous` |  |  |  |
|  |  |  | `latency_or_generation_issue` |  |  |  |

## Categorii prioritare

Prioritatea review-ului manual ar trebui sa fie:

1. `intrebari_vagi_ambigue` - pass rate 16%, pentru calibrarea clarificarilor.
2. `calendar_academic` - pass rate 39%, pentru verificarea surselor si a indexului.
3. `intrebari_fara_raspuns_sigur` - pass rate 43%, pentru refuz prudent si confidence low.
4. `regulamente_metodologii` - pass rate 59%, pentru ranking pe documente oficiale.

## Reguli de review

- Nu modifica rezultatele istorice ale evaluarii.
- Nu schimba datasetul pentru a creste artificial scorul.
- Noteaza separat cazurile in care evaluatorul automat este prea strict.
- Daca o sursa lipseste din index, marcheaza problema ca index/crawler, nu ca generatie.
- Daca raspunsul este formulat prea sigur fara dovezi, marcheaza confidence si guard behavior.
