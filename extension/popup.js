"use strict";

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

const INDEXING_POLL_MS = 2000;
const refs = UVTRender.createRefs();

let indexingPollId = null;
let backendAvailable = false;

function updateControls() {
  UVTRender.updateControlState(refs, {
    ...UVTState.getSnapshot(),
    backendAvailable
  });
}

function setBusy(busy) {
  UVTState.setSending(busy);
  updateControls();
}

function setIndexingBusy(busy) {
  UVTState.setIndexing(busy);
  updateControls();
}

function startIndexingPoll() {
  if (!indexingPollId) {
    indexingPollId = setInterval(checkIndexingStatus, INDEXING_POLL_MS);
  }
}

function stopIndexingPoll() {
  if (indexingPollId) {
    clearInterval(indexingPollId);
    indexingPollId = null;
  }
}

function isBackendOnline() {
  return backendAvailable;
}

function setBackendAvailability(online) {
  backendAvailable = Boolean(online);
  UVTRender.setBackendOnline(refs, backendAvailable);
  updateControls();
}

async function setBackendUnavailableStatus() {
  const backendUrl = await UVTApi.getBackendUrl();
  const hasSavedConversation = UVTRender.hasConversation(refs);
  setBackendAvailability(false);
  UVTRender.setStatus(
    refs,
    "error",
    "Backend local indisponibil",
    hasSavedConversation
      ? `Se afișează conversația salvată. Pentru răspunsuri noi, pornește Flask pe ${backendUrl}.`
      : `Pornește Flask pe ${backendUrl}. Dacă folosești alt URL local, verifică Opțiunile extensiei.`
  );
}

function handleIndexingStatus(indexing) {
  const running = Boolean(indexing?.running);
  setIndexingBusy(running);
  UVTRender.renderIndexingProgress(refs, indexing);

  if (running) {
    setBackendAvailability(true);
    UVTRender.setStatus(
      refs,
      "loading",
      "Indexare surse oficiale",
      indexing.message || "Backend-ul construiește indexul local complet."
    );
    startIndexingPoll();
    return true;
  }

  stopIndexingPoll();
  if (indexing?.error) {
    UVTRender.setStatus(
      refs,
      "warning",
      "Indexarea a eșuat",
      indexing.error || "Verifică serviciile locale și logurile backend."
    );
  }
  return false;
}

async function checkIndexingStatus() {
  try {
    const data = await UVTApi.getIndexingStatus();
    const stillRunning = handleIndexingStatus(data?.indexing);
    if (!stillRunning) {
      await checkBackend();
    }
  } catch {
    stopIndexingPoll();
    setIndexingBusy(false);
    await setBackendUnavailableStatus();
  }
}

async function checkBackend() {
  try {
    const data = await UVTApi.checkBackend();
    const chunkCount = Number(data.index?.chunk_count || 0);
    const vectorCount = Number(data.vector_index?.points_count || 0);
    const builtAt = data.index?.built_at || "necunoscut";
    const generationModel = data.ollama?.generation_model || "Ollama";
    const embeddingModel = data.ollama?.embedding_model || "embedding local";
    const healthMessages = UVTRender.buildHealthMessages(data);

    setBackendAvailability(true);
    if (handleIndexingStatus(data.indexing)) {
      refs.emptyText.textContent = "Indexarea oficială rulează. Întrebările vor fi disponibile după finalizare.";
      return true;
    }

    if (data.status === "ok") {
      UVTRender.setStatus(
        refs,
        "idle",
        "Sistem local pregătit",
        `Index oficial: ${chunkCount} fragmente. Vectori: ${vectorCount}. Model răspuns: ${generationModel}. Embedding: ${embeddingModel}. Build: ${builtAt}.`
      );
    } else {
      UVTRender.setStatus(
        refs,
        "warning",
        "Sistem local parțial disponibil",
        healthMessages.length ? healthMessages.join(" ") : "Unele componente locale nu sunt complet disponibile."
      );
    }
    refs.emptyText.textContent = "Exemple: orar, secretariat, admitere, burse, reguli despre cumularea burselor.";
    return true;
  } catch {
    stopIndexingPoll();
    setIndexingBusy(false);
    await setBackendUnavailableStatus();
    refs.emptyText.textContent = "Extensia rămâne disponibilă, dar nu poate trimite întrebări până când backendul local nu răspunde.";
    return false;
  }
}

async function loadFaculties() {
  const saved = await UVTStorage.loadFacultyId();
  try {
    const data = await UVTApi.getFaculties();
    UVTRender.populateFaculties(refs, data.faculties || FALLBACK_FACULTIES, saved);
    setBackendAvailability(true);
  } catch {
    UVTRender.populateFaculties(refs, FALLBACK_FACULTIES, saved);
  }
}

async function saveCurrentConversation() {
  await UVTStorage.saveConversationHistory(refs.faculty.value || "uvt", UVTState.getHistory());
}

async function loadConversationHistory(facultyId) {
  const items = await UVTStorage.loadConversationHistory(facultyId);
  UVTState.setHistory(items);
  UVTRender.renderConversation(refs, UVTState.getHistory(), { onFeedback: handleFeedback });
  if (items.length > 0 && !isBackendOnline()) {
    await setBackendUnavailableStatus();
  }
  updateControls();
}

async function rememberRecentQuestion(question) {
  const recent = await UVTStorage.saveRecentQuestion(question);
  UVTRender.renderRecentQuestions(refs, recent, sendMessage);
}

async function loadRecentQuestions() {
  const recent = await UVTStorage.loadRecentQuestions();
  UVTRender.renderRecentQuestions(refs, recent, sendMessage);
}

async function loadTheme() {
  const theme = await UVTStorage.loadTheme();
  UVTRender.applyTheme(refs, theme);
}

async function toggleTheme() {
  const next = document.body.classList.contains("dark") ? "light" : "dark";
  UVTRender.applyTheme(refs, next);
  await UVTStorage.saveTheme(next);
}

async function handleFeedback(payload) {
  try {
    await UVTApi.postFeedback(payload);
    setBackendAvailability(true);
  } catch (error) {
    setBackendAvailability(false);
    throw error;
  }
}

async function clearConversation() {
  UVTState.clearHistory();
  await saveCurrentConversation();
  UVTRender.renderConversation(refs, UVTState.getHistory(), { onFeedback: handleFeedback });
  if (backendAvailable) {
    UVTRender.setStatus(refs, "idle", "Conversație ștearsă", "Poți începe o întrebare nouă pentru facultatea selectată.");
  } else {
    await setBackendUnavailableStatus();
  }
  updateControls();
}

function fallbackCopyText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  fallbackCopyText(text);
}

async function copyLastAnswer() {
  const last = UVTState.getLastAssistantMessage();
  if (!last) {
    return;
  }

  try {
    await copyText(last.text);
    const previousLabel = refs.copyAnswer.textContent;
    refs.copyAnswer.textContent = "Copiat";
    UVTRender.setStatus(refs, "success", "Răspuns copiat", "Ultimul răspuns al asistentului a fost copiat.");
    setTimeout(() => {
      refs.copyAnswer.textContent = previousLabel;
    }, 1200);
  } catch {
    UVTRender.setStatus(refs, "warning", "Copiere nereușită", "Browserul nu a permis accesul la clipboard.");
  }
}

async function sendMessage(prefilledQuestion = null) {
  if (UVTState.isSending()) {
    return;
  }

  if (!backendAvailable) {
    await setBackendUnavailableStatus();
    return;
  }

  if (UVTState.isIndexing()) {
    UVTRender.setStatus(
      refs,
      "loading",
      "Indexare surse oficiale",
      "Așteaptă finalizarea indexării înainte de a trimite o întrebare."
    );
    return;
  }

  const question = (prefilledQuestion ?? refs.input.value).trim();
  if (!question) {
    refs.input.focus();
    return;
  }

  await rememberRecentQuestion(question);
  const facultyId = refs.faculty.value || (await UVTStorage.loadFacultyId()) || "uvt";
  const history = UVTState.buildHistoryPayload();

  setBusy(true);
  UVTRender.setStatus(refs, "loading", "Analizez întrebarea", "Caut semantic în Qdrant local.");
  UVTRender.addUserMessage(refs, question);
  refs.input.value = "";
  UVTRender.addLoadingMessage(refs);

  try {
    const data = await UVTApi.sendChatMessage({ question, facultyId, history });
    const sources = UVTState.normalizeSources(data.sources || []);
    const answer = data.answer || "Nu există răspuns disponibil.";

    UVTRender.removeLoadingMessage();

    if (data.confidence === "low") {
      UVTRender.setStatus(refs, "warning", "Dovezi parțiale", "Răspunsul este limitat de sursele oficiale găsite.");
    } else {
      UVTRender.setStatus(
        refs,
        "success",
        "Răspuns pregătit",
        "Răspuns generat local cu Ollama din sursele indexate local."
      );
    }

    UVTRender.addBotMessage(
      refs,
      answer,
      sources,
      {
        source: "popup",
        question,
        answer,
        faculty_id: facultyId,
        matched_faculty: data.matched_faculty || "UVT",
        confidence: data.confidence || "low",
        confidence_score: data.confidence_score || 0,
        live_verified: Boolean(data.live_verified),
        retrieval_backend: data.retrieval_backend || "unknown",
        generation_mode: data.generation_mode || "unknown",
        generation_error: data.generation_error || "",
        evidence: data.evidence || {},
        sources
      },
      handleFeedback
    );

    UVTState.appendHistory("user", question);
    UVTState.appendHistory("assistant", answer, sources, {
      confidence: data.confidence || "",
      confidence_score: data.confidence_score || 0,
      confidence_reason: data.confidence_reason || "",
      live_verified: Boolean(data.live_verified),
      retrieval_backend: data.retrieval_backend || "",
      generation_mode: data.generation_mode || "",
      evidence: data.evidence || {}
    });
    await saveCurrentConversation();
    setBackendAvailability(true);
  } catch (error) {
    UVTRender.removeLoadingMessage();
    if (error.payload?.indexing) {
      handleIndexingStatus(error.payload.indexing);
      setBackendAvailability(true);
      UVTRender.addBotMessage(refs, error.payload.answer || "Indexarea este în curs. Încearcă după finalizare.");
      return;
    }
    setBackendAvailability(false);
    const backendUrl = await UVTApi.getBackendUrl();
    UVTRender.setStatus(
      refs,
      "error",
      "Backend local indisponibil",
      `Nu s-a putut trimite întrebarea. Pornește Flask pe ${backendUrl} și încearcă din nou.`
    );
    UVTRender.addBotMessage(
      refs,
      `Nu m-am putut conecta la backendul Flask local (${backendUrl}). Verifică Ollama, Qdrant, Flask și URL-ul din Opțiunile extensiei.`
    );
  } finally {
    setBusy(false);
  }
}

refs.faculty.addEventListener("change", async () => {
  await UVTStorage.saveFacultyId(refs.faculty.value);
  UVTRender.updateFacultyBadge(refs);
  await loadConversationHistory(refs.faculty.value);
});

refs.send.addEventListener("click", () => sendMessage());
refs.themeToggle.addEventListener("click", toggleTheme);
refs.clearConversation.addEventListener("click", clearConversation);
refs.copyAnswer.addEventListener("click", copyLastAnswer);

refs.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

refs.chips.forEach((chip) => {
  chip.addEventListener("click", () => sendMessage(chip.dataset.q || ""));
});

(async function init() {
  updateControls();
  await loadTheme();
  await checkBackend();
  await loadFaculties();
  await loadConversationHistory(refs.faculty.value);
  await loadRecentQuestions();
})();
