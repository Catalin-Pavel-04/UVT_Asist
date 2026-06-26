"use strict";

(function exposeContent(global) {
  const FALLBACK_FACULTIES = [
    { id: "uvt", name: "UVT (general)" },
    { id: "arte", name: "Facultatea de Arte și Design" },
    { id: "cbg", name: "Facultatea de Chimie, Biologie, Geografie" },
    { id: "drept", name: "Facultatea de Drept" },
    { id: "feaa", name: "Facultatea de Economie și de Administrare a Afacerilor" },
    { id: "sport", name: "Facultatea de Educație Fizică și Sport" },
    { id: "ffm", name: "Facultatea de Fizică și Matematică" },
    { id: "info", name: "Facultatea de Informatică" },
    { id: "fmt", name: "Facultatea de Muzică și Teatru" },
    { id: "lift", name: "Facultatea de Litere, Istorie, Filosofie și Teologie" },
    { id: "fsas", name: "Facultatea de Sociologie și Asistență Socială" },
    { id: "fpse", name: "Facultatea de Psihologie și Științe ale Educației" },
    { id: "fsgc", name: "Facultatea de Științe ale Guvernării și Comunicării" }
  ];

  const TEXT = {
    backendUnavailableTitle: "Backendul local nu răspunde",
    savedConversationOffline: (backendUrl) =>
      `Poți citi conversația salvată. Pentru un răspuns nou, pornește Flask la ${backendUrl}.`,
    startBackend: (backendUrl) =>
      `Pornește Flask la ${backendUrl}. Dacă ai schimbat adresa, verifică pagina de opțiuni.`,
    indexingTitle: "Indexez sursele oficiale",
    indexingMessage: "Backendul pregătește indexul local. Durează puțin la primul build.",
    indexingFailedTitle: "Indexarea s-a oprit",
    indexingFailedMessage: "Verifică serviciile locale și logurile backendului.",
    indexingEmpty: "Încă indexez sursele oficiale. Poți trimite întrebări după ce se termină.",
    readyTitle: "Gata de întrebări",
    readyDetails: ({ chunkCount, vectorCount, generationModel, embeddingModel, builtAt }) =>
      `Am ${chunkCount} fragmente oficiale și ${vectorCount} vectori locali. Răspuns: ${generationModel}. Embedding: ${embeddingModel}. Build: ${builtAt}.`,
    partialTitle: "Mai lipsește ceva",
    partialMessage: "Unele servicii locale nu sunt complet disponibile.",
    examples: "Poți întreba despre orar, secretariat, admitere, burse sau regulile de cumul.",
    backendOfflineEmpty: "Poți răsfoi conversațiile salvate, dar pentru întrebări noi trebuie pornit backendul local.",
    conversationClearedTitle: "Conversație ștearsă",
    conversationClearedText: "Poți începe o întrebare nouă pentru facultatea selectată.",
    answerCopiedTitle: "Răspuns copiat",
    answerCopiedText: "Ultimul răspuns este acum în clipboard.",
    copyFailedTitle: "Nu am putut copia",
    copyFailedText: "Browserul nu a permis accesul la clipboard.",
    waitForIndexing: "Așteaptă finalizarea indexării înainte de a trimite întrebarea.",
    analyzingTitle: "Caut în sursele oficiale",
    analyzingText: "Verific indexul local și aleg cele mai relevante pagini.",
    noAnswer: "Nu am găsit un răspuns suficient de sigur.",
    weakEvidenceTitle: "Dovezi parțiale",
    weakEvidenceText: "Am găsit doar surse oficiale parțial relevante, deci răspunsul trebuie citit prudent.",
    answerReadyTitle: "Am găsit un răspuns",
    answerReadyText: "Răspunsul a fost pregătit local, pe baza surselor indexate.",
    indexingAnswer: "Indexarea este încă în curs. Încearcă din nou după finalizare.",
    sendFailed: (backendUrl) =>
      `Nu am putut trimite întrebarea. Pornește Flask la ${backendUrl} și încearcă din nou.`,
    backendConnectionFailed: (backendUrl) =>
      `Nu mă pot conecta la backendul Flask local (${backendUrl}). Verifică Ollama, Qdrant, Flask și adresa din opțiunile extensiei.`,
    backendUnavailableTooltip: "Pornește backendul Flask local pentru a trimite întrebări.",
    sourceDefaultTitle: "Sursă oficială",
    localIndexBadge: "Index local",
    localIndexTooltip: "Sursa provine din indexul local.",
    savingFeedback: "Se salvează...",
    savedFeedback: "Salvat",
    failedFeedback: "Netrimis",
    confidenceLabel: (confidence, score) =>
      Number.isFinite(score) && score > 0
        ? `Încredere ${confidence} (${Math.round(score)})`
        : `Încredere ${confidence}`,
    localIndexMeta: "Răspuns construit din sursele indexate local.",
    sourceCount: (sourceCount) => `${sourceCount} ${sourceCount === 1 ? "sursă" : "surse"}`,
    ollamaUnavailable: "Ollama local nu răspunde. Pornește `ollama serve`.",
    generationModelMissing: (model) => `Modelul local de generare lipsește. Rulează \`ollama pull ${model}\`.`,
    embeddingModelMissing: (model) => `Modelul local de embedding lipsește. Rulează \`ollama pull ${model}\`.`,
    jsonIndexMissing: "Indexul local lipsește. Rulează `python backend/build_index.py`.",
    qdrantUnavailable: "Qdrant local este indisponibil. Rulează `docker compose up -d qdrant`.",
    qdrantEmpty: "Qdrant nu are vectori indexați. Pornește Qdrant și reconstruiește indexul.",
    indexVectorMismatch: "Numărul de chunks din JSON nu corespunde cu punctele din Qdrant. Rulează `python backend/scripts/build_vector_index.py`.",
    lightTheme: "Light",
    darkTheme: "Dark",
    lightThemeTitle: "Comută pe tema deschisă",
    darkThemeTitle: "Comută pe tema închisă"
  };

  global.UVTContent = {
    FALLBACK_FACULTIES,
    TEXT
  };
})(globalThis);
