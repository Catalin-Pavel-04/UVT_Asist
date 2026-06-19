# Checklist demo

## Înainte de demo

- Rulează verificarea locală:

```powershell
python backend/scripts/demo_check.py
```

- Pornește Qdrant:

```powershell
docker compose up -d qdrant
```

- Pornește Ollama:

```powershell
ollama serve
```

- Verifică modelele Ollama: `qwen3:4b` și `nomic-embed-text`.
- Dacă lipsesc modelele, rulează:

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

- Dacă indexul lipsește, rulează:

```powershell
python backend/build_index.py
```

- Pornește backend-ul:

```powershell
python backend/app.py
```

- Verifică endpoint-ul `/health`: `http://127.0.0.1:5000/health`.
- Încarcă extensia Chrome din folderul `extension/`.

## Întrebări de demonstrat

- `Unde găsesc orarul la Informatică?`
  Comportament așteptat: sursă oficială `info.uvt.ro/orare`.
- `Unde găsesc secretariatul Facultății de Informatică?`
  Comportament așteptat: sursă oficială de contact/secretariat.
- `Este posibil ca un student să beneficieze de 2 burse?`
  Comportament așteptat: metodologie/regulament burse.
- `Cum se depune dosarul pentru creditele de voluntariat?`
  Comportament așteptat: pagină/sursă oficială despre credite sau portofoliu de voluntariat.
- `Care va fi media minimă de admitere de anul viitor?`
  Comportament așteptat: confidence low sau răspuns că sursele oficiale nu sunt suficiente.

## Ce trebuie arătat comisiei

- Statusul backend-ului.
- Sursele oficiale.
- Confidence score.
- Verificare live sau index local.
- Evaluarea RAG.
- Fallback pentru întrebări nesigure.
