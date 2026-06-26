# Asistenta AI

Acest document descrie transparent modul in care asistenta AI a fost folosita in proiect. Scopul este asumarea instrumentelor folosite, nu mascarea lor.

## Instrumente folosite

Au fost folosite instrumente AI pentru asistenta in dezvoltare, documentare si evaluare, inclusiv ChatGPT/Codex in sesiuni locale de lucru.

In runtime, aplicatia foloseste Ollama local pentru:

- generarea raspunsurilor;
- embeddings;
- analiza JSON a query-ului, cand este activata.

Nu sunt folosite API-uri AI externe in fluxul runtime al aplicatiei.

## Pentru ce a fost folosita asistenta AI

Asistenta AI a fost folosita pentru:

- generarea si rafinarea unor fragmente de cod;
- explicarea si structurarea documentatiei;
- construirea unor scripturi de evaluare si raportare;
- generarea independenta a datasetului Q&A 1000 cu asistenta ChatGPT;
- redactarea rubricilor de evaluare si a interpretarilor, cu verificare ulterioara de catre autor.

## Pentru ce nu a fost folosita asistenta AI

Asistenta AI nu este sursa oficiala UVT. Raspunsurile aplicatiei trebuie sa fie fundamentate pe surse oficiale indexate local, nu pe cunostintele generale ale unui model.

Modelul generativ nu alege sursele finale. Sursele sunt selectate prin retrieval, filtre metadata si reranking determinist.

Benchmarkul Q&A 1000 nu a fost folosit pentru tuningul aplicatiei. El a fost folosit pentru evaluare finala si raportare.

## Ce a verificat autorul

Autorul a verificat:

- rularea locala a backendului Flask;
- endpointurile publice folosite de extensie;
- indexarea si reconstructia vectorilor;
- rularea testelor pytest;
- rapoartele Q&A 1000 si valorile folosite in documentatie;
- faptul ca sursele expuse in popup sunt URL-uri oficiale UVT sau ale facultatilor.

## Datasetul Q&A 1000

Datasetul Q&A 1000 este declarat explicit ca dataset sintetic, independent, generat cu asistenta ChatGPT si folosit pentru evaluare. Metadata din dataset pastreaza aceasta informatie (`created_by`, `generation_method`, `purpose`).

Aceasta transparenta este pastrata intentionat in repository si in documentatie.
