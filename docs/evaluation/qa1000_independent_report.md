# Raport evaluare Q&A 1000 independent

## Scopul evaluarii

Acest raport sintetizeaza rezultatele evaluatorului independent de 1000 de intrebari pentru UVT_Asist. Evaluatorul trimite intrebarile catre backendul local si compara raspunsurile cu rubricile definite in dataset.

## Descrierea datasetului

| Camp | Valoare |
| --- | --- |
| Dataset | backend\evaluation\eval_qa_1000_independent.json |
| Run label | final_1000 |
| Backend URL | http://127.0.0.1:5000 |
| Started at | 2026-06-25T13:16:19Z |
| Finished at | 2026-06-26T16:12:08Z |
| Total in fisierul evaluat | 1000 |
| Dataset metadata: categories | {"admitere": 100, "burse": 100, "calendar_academic": 100, "cazare_camine": 100, "contact_secretariat": 100, "intrebari_fara_raspuns_sigur": 100, "intrebari_vagi_ambigue": 100, "orar": 100, "regulamente_metodologii": 100, "voluntariat_credite": 100} |
| Dataset metadata: created_by | ChatGPT |
| Dataset metadata: generation_method | synthetic_template_curated_by_chatgpt |
| Dataset metadata: important_note | Răspunsurile ideale sunt rubrici textuale și răspunsuri-model orientate pe comportamentul așteptat: surse oficiale, refuz/clarificare când lipsesc dovezile, confidence și evitarea afirmațiilor speculative. Pentru date administrative variabile, benchmarkul nu impune date exacte neverificate. |
| Dataset metadata: language | ro |
| Dataset metadata: name | UVT Asist independent Q&A 1000 benchmark |
| Dataset metadata: purpose | Evaluare finală și raportare în documentație, nu tuning al aplicației. |
| Dataset metadata: question_count | 1000 |
| Dataset metadata: seed | 202606 |
| Dataset metadata: version | 2026-06-independent-v1 |

## Distributia pe categorii

| Categorie | Numar intrebari |
| --- | ---: |
| admitere | 100 |
| burse | 100 |
| calendar_academic | 100 |
| cazare_camine | 100 |
| contact_secretariat | 100 |
| intrebari_fara_raspuns_sigur | 100 |
| intrebari_vagi_ambigue | 100 |
| orar | 100 |
| regulamente_metodologii | 100 |
| voluntariat_credite | 100 |

## Metodologia de scoring

Scorul principal nu compara raspunsul text-la-text cu ideal_answer. Pentru intrebarile cu raspuns asteptat, scorul combina potrivirea URL-urilor Top-1/Top-3, page_type, intent, required_terms, confidence si penalizarea pentru forbidden_terms. Pentru intrebarile fara raspuns sigur, scorul favorizeaza confidence low, lipsa dovezilor suficiente si formularea prudenta de refuz sau clarificare. ideal_overlap_score ramane doar metric informativ.

## Rezultate globale

| Metrica | Valoare |
| --- | ---: |
| Total intrebari | 1000 |
| Raspunsuri generate | 1000 |
| Passed | 644 |
| Failed | 356 |
| Pass rate | 64.4% |
| Scor mediu | 72.34 |
| Scor median | 82.35 |
| Overlap ideal mediu | 12.82 |
| Top-1 URL match | 439/694 (63.26%) |
| Top-3 URL match | 502/694 (72.33%) |
| Confidence match | 843/1000 (84.30%) |
| Erori | 0 |

## Rezultate pe categorii

| Categorie | Total | Pass rate | Scor mediu | Top-1 URL | Top-3 URL | Latenta medie | Erori |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| admitere | 100 | 80.0% | 78.35 | 44/100 | 66/100 | 35.278 | 0 |
| burse | 100 | 65.0% | 78.29 | 92/100 | 93/100 | 26.984 | 0 |
| calendar_academic | 100 | 39.0% | 60.12 | 26/100 | 39/100 | 15.221 | 0 |
| cazare_camine | 100 | 87.0% | 84.7 | 91/100 | 92/100 | 23.703 | 0 |
| contact_secretariat | 100 | 92.0% | 89.36 | 46/54 | 46/54 | 26.135 | 0 |
| intrebari_fara_raspuns_sigur | 100 | 43.0% | 57.45 | 0/0 | 0/0 | 18.963 | 0 |
| intrebari_vagi_ambigue | 100 | 16.0% | 37.5 | 0/0 | 0/0 | 20.095 | 0 |
| orar | 100 | 68.0% | 74.76 | 24/40 | 24/40 | 24.294 | 0 |
| regulamente_metodologii | 100 | 59.0% | 72.57 | 19/100 | 42/100 | 17.358 | 0 |
| voluntariat_credite | 100 | 95.0% | 90.27 | 97/100 | 100/100 | 25.203 | 0 |

## Latente

| Metrica | Secunde |
| --- | ---: |
| Medie | 23.323 |
| Mediana | 24.335 |
| P75 | 32.971 |
| P90 | 39.986 |
| P95 | 51.269 |
| Max | 149.611 |

## Distributie confidence

| Confidence | Numar |
| --- | ---: |
| high | 773 |
| medium | 118 |
| low | 109 |

## Distributie retrieval_backend

| Retrieval backend | Numar |
| --- | ---: |
| qdrant | 910 |
| clarification | 58 |
| unsupported_guard | 32 |

## Distributie generation_mode

| Generation mode | Numar |
| --- | ---: |
| ollama | 458 |
| local_source_navigation | 347 |
| fallback_ollama_error | 105 |
| none | 61 |
| clarification | 29 |

## Top esecuri

| ID | Categorie | Scor | Confidence | Top-1 URL | Eroare |
| --- | --- | ---: | --- | --- | --- |
| intrebari_fara_raspuns_sigur_0014 | intrebari_fara_raspuns_sigur | 0.0 | high | https://info.uvt.ro/wp-content/uploads/2025/10/Metodologie-de-acordare-a-burselor-2025-2026.pdf |  |
| calendar_academic_0015 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0027 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0094 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0060 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0023 | calendar_academic | 0.0 | low |  |  |
| cazare_camine_0051 | cazare_camine | 0.0 | low |  |  |
| calendar_academic_0007 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0017 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0051 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0048 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0026 | calendar_academic | 0.0 | low |  |  |
| cazare_camine_0086 | cazare_camine | 0.0 | low |  |  |
| calendar_academic_0045 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0046 | calendar_academic | 0.0 | low |  |  |
| calendar_academic_0043 | calendar_academic | 11.76 | medium | https://admitere.uvt.ro/wp-content/uploads/2024/08/Regulament-de-cazare-in-caminele-UVT.pdf |  |
| contact_secretariat_0081 | contact_secretariat | 11.76 | high | https://uvt.ro/blog/uvt-tine-cont-de-sugestiile-elevilor-si-adapteaza-programul-de-pregatire-pentru-bac |  |
| cazare_camine_0087 | cazare_camine | 11.76 | high | https://uvt.ro/wp-content/uploads/2026/01/Anexa-1.-Regulament-privind-utilizarea-AI-in-educatie-la-UVT.pdf |  |
| calendar_academic_0066 | calendar_academic | 11.76 | medium | https://admitere.uvt.ro/wp-content/uploads/2024/08/Regulament-de-cazare-in-caminele-UVT.pdf |  |
| calendar_academic_0078 | calendar_academic | 19.61 | high | https://uvt.ro/wp-content/uploads/2026/02/Anexa-2.-Regulament-admitere-licenta-UVT-2026-2027_modif.-1.pdf |  |

## Cele mai lente intrebari

| ID | Categorie | Latenta | Scor | Generation mode | Top-1 URL |
| --- | --- | ---: | ---: | --- | --- |
| contact_secretariat_0011 | contact_secretariat | 149.611 | 100.0 | ollama | https://uvt.ro/contact |
| orar_0012 | orar | 67.078 | 83.33 | fallback_ollama_error | https://lift.uvt.ro/orare |
| admitere_0058 | admitere | 66.524 | 58.82 | ollama | https://lift.uvt.ro/calendar-admitere-lift-studii-de-licenta |
| admitere_0070 | admitere | 65.305 | 58.82 | fallback_ollama_error | https://uvt.ro/blog/a-inceput-procesul-de-admitere-la-uvt |
| admitere_0093 | admitere | 64.402 | 58.82 | fallback_ollama_error | https://cbg.uvt.ro/arhiva |
| admitere_0038 | admitere | 64.381 | 88.24 | fallback_ollama_error | https://info.uvt.ro/admitere-licenta |
| admitere_0036 | admitere | 63.624 | 58.82 | fallback_ollama_error | https://drept.uvt.ro/admitere-master-rezultate-si-alte-anunturi.html |
| orar_0047 | orar | 63.472 | 83.33 | fallback_ollama_error | https://feaa.uvt.ro/fisiere/studenti/licenta/2025-2026/orare/orar-id-sem-i-2025-2026-ataa-online.pdf |
| admitere_0029 | admitere | 63.175 | 76.47 | fallback_ollama_error | https://sport.uvt.ro/managementul-activitatilor-si-organizatiilor-de-educatie-fizica-si-sportive |
| admitere_0095 | admitere | 63.162 | 58.82 | fallback_ollama_error | https://uvt.ro/wp-content/uploads/2021/05/Anexa-3.-Metodologie-admitere-FMT-master-2021-editia-a-II-a.pdf |

## Interpretare prudenta

Rezultatele trebuie interpretate ca performanta pe setul definit de evaluare, nu ca garantie universala. Setul acopera scenarii reprezentative, dar nu toate formularile posibile ale studentilor.

## Limitari

- Scorul automat foloseste rubrici si semnale observabile, nu o evaluare umana completa.
- Rezultatele depind de starea indexului local, de modelele Ollama configurate si de disponibilitatea Qdrant.
- Latentele sunt masurate in mediul local in care a fost rulata evaluarea.
- Intrebarile fara raspuns sigur sunt evaluate separat pentru a recompensa refuzul prudent in locul raspunsurilor speculative.
