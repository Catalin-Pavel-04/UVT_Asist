# Cazuri de esec si refuz controlat

Un asistent RAG administrativ trebuie sa evite raspunsurile nesustinute. Pentru UVT_Asist, este mai sigur ca sistemul sa ceara clarificari sau sa declare lipsa dovezilor decat sa ofere informatii inventate despre reguli, termene, burse, admitere sau decizii administrative.

## Cazuri unde sistemul trebuie sa ceara clarificari

Exemple:

- `Unde gasesc orarul?` fara facultate selectata sau mentionata, cand utilizatorul este in context UVT general.
- `Unde gasesc secretariatul?` fara facultate, cand nu este clar daca se cere contactul UVT central sau secretariatul unei facultati.
- `Am o problema cu facultatea, unde ma uit?`
- `Vreau informatii importante pentru mine.`
- `Ce trebuie sa fac ca student?`

Motiv: intrebarea este prea vaga sau depinde de facultate. Alegerea unei surse concrete fara clarificare ar putea duce la un raspuns gresit.

## Cazuri unde sistemul trebuie sa refuze un raspuns sigur

Exemple:

- `Ce bursa voi primi eu luna viitoare?`
- `Voi primi loc la camin anul acesta?`
- `Care va fi media minima de admitere anul viitor?`
- `Ce decizie va lua comisia pentru dosarul meu?`
- `Profesorul X va lipsi maine?`
- `Care este parola mea de StudentWeb?`
- `Poti garanta ca intru la buget?`

Motiv: raspunsul cere predictii, decizii personale, date private sau informatii care nu pot fi confirmate din sursele oficiale indexate.

## Cazuri unde sursele pot fi incomplete

Exemple:

- `Ce acte trebuie daca situatia mea familiala este foarte specifica?`
- `Unde obtin fiecare document justificativ pentru bursa sociala?`
- `Care este taxa exacta peste doi ani?`
- `Ce se intampla daca regulamentul a fost modificat ieri?`

Motiv: chiar daca sistemul gaseste o metodologie sau un regulament, unele detalii pot lipsi, pot depinde de situatia personala sau pot necesita confirmare administrativa directa.

## De ce este important sa nu inventeze

Inventarea raspunsurilor este riscanta in contexte universitare deoarece poate afecta decizii reale ale studentilor:

- depunerea gresita a unui dosar;
- ratarea unui termen;
- interpretarea incorecta a unei metodologii;
- alegerea unei surse neoficiale;
- divulgarea de date personale intr-un context nepotrivit.

De aceea, backendul returneaza confidence si surse oficiale, iar promptul cere modelului local sa raspunda numai din contextul selectat. Cand dovezile sunt slabe, sistemul trebuie sa spuna clar ca sursele oficiale recuperate sunt insuficiente.

## Comportament asteptat

Pentru cazurile de mai sus, comportamentul dorit este:

- confidence `low`;
- raspuns care explica limitarea;
- zero sau putine surse, doar daca sunt oficiale si relevante partial;
- fara reguli, termene sau decizii inventate;
- cerere de clarificare cand problema este facultatea, categoria sau contextul.

Acest comportament este parte din strategia de reducere a halucinatiilor si este inclus in evaluarea proiectului.
