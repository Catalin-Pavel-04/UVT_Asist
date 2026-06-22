# Evaluare comparativa Q&A 100 intrebari

Rapoarte comparate:

- Inainte de optimizari: `backend/data/evaluation/qa_eval_results_20260617T143927Z.json`
- Dupa optimizari: `backend/data/evaluation/qa_eval_results_20260617T170750Z.json`

## Rezumat global

| Indicator | Inainte | Dupa | Diferenta |
| --- | ---: | ---: | ---: |
| Intrebari evaluate | 100 | 100 | 0 |
| Raspunsuri trecute | 65 | 100 | +35 |
| Rata de trecere | 65% | 100% | +35 pp |
| Raspunsuri esuate | 35 | 0 | -35 |
| Scor mediu Q&A | 69.54 | 85.84 | +16.30 |
| Scor median Q&A | 82.0 | 85.0 | +3.0 |
| Top-1 URL corect | 98/100 | 100/100 | +2 |
| Top-3 URL corect | 98/100 | 100/100 | +2 |
| Potrivire nivel incredere | 83/100 | 99/100 | +16 |
| Intrebari fara raspuns sigur tratate corect | 1/10 | 10/10 | +9 |
| Latenta medie | 27.182s | 13.679s | -13.503s |
| Latenta mediana | 37.689s | 4.342s | -33.347s |

## Rezultat pe categorii

| Categorie | Inainte | Dupa | Esecuri inainte -> dupa | Scor mediu inainte -> dupa |
| --- | ---: | ---: | ---: | ---: |
| admitere | 10/10 | 10/10 | 0 -> 0 | 85.2 -> 85.6 |
| burse | 10/10 | 10/10 | 0 -> 0 | 83.5 -> 83.8 |
| calendar academic | 2/10 | 10/10 | 8 -> 0 | 61.6 -> 85.4 |
| cazare/camine | 7/10 | 10/10 | 3 -> 0 | 75.1 -> 83.0 |
| contact/secretariat | 5/10 | 10/10 | 5 -> 0 | 68.8 -> 84.9 |
| intrebari fara raspuns sigur in sursele oficiale | 1/10 | 10/10 | 9 -> 0 | 26.5 -> 100.0 |
| intrebari vagi | 3/10 | 10/10 | 7 -> 0 | 53.4 -> 81.2 |
| orar | 8/10 | 10/10 | 2 -> 0 | 76.1 -> 84.5 |
| regulamente/metodologii | 9/10 | 10/10 | 1 -> 0 | 79.2 -> 83.8 |
| voluntariat/credite | 10/10 | 10/10 | 0 -> 0 | 86.0 -> 86.2 |

## Interpretare

Aplicatia a trecut de la 65% la 100% rata de trecere pe setul de 100 de intrebari. Cele mai mari imbunatatiri au fost pe:

- intrebari fara raspuns sigur: de la 1/10 la 10/10;
- calendar academic: de la 2/10 la 10/10;
- intrebari vagi: de la 3/10 la 10/10;
- contact/secretariat: de la 5/10 la 10/10.

Imbunatatirile au venit din doua directii principale:

- selectia surselor oficiale a devenit mai determinista pentru cazuri cunoscute, precum orar, contact UVT, calendar academic, cazare si regulamente;
- aplicatia refuza sau cere clarificari pentru intrebari personale, predictive sau prea vagi, in loc sa genereze raspunsuri speculative.

Latenta medie a scazut de la 27.182s la 13.679s, iar latenta mediana de la 37.689s la 4.342s. Diferenta mare intre medie si mediana arata ca majoritatea intrebarilor sunt rapide, dar unele intrebari care ating documente PDF sau generarea Ollama raman mai lente.
