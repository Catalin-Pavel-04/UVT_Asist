const BACKEND_URL = "http://127.0.0.1:5000";
const RECENT_QUESTIONS_KEY = "recentQuestions";
const MAX_HISTORY_MESSAGES = 10;
const INDEXING_POLL_MS = 2000;
const REQUEST_TIMEOUT_MS = {
  health: 6000,
  faculties: 6000,
  feedback: 8000,
  chat: 150000
};

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

const refs = {
  log: document.getElementById("log"),
  input: document.getElementById("q"),
  send: document.getElementById("send"),
  faculty: document.getElementById("faculty"),
  facultyBadge: document.getElementById("facultyBadge"),
  confidenceBadge: document.getElementById("confidenceBadge"),
  verificationBadge: document.getElementById("verificationBadge"),
  metaLine: document.getElementById("metaLine"),
  emptyState: document.getElementById("emptyState"),
  emptyText: document.getElementById("emptyText"),
  statusDot: document.getElementById("statusDot"),
  themeToggle: document.getElementById("themeToggle"),
  recentQuestions: document.getElementById("recentQuestions"),
  statusPanel: document.getElementById("statusPanel"),
  statusTitle: document.getElementById("statusTitle"),
  statusText: document.getElementById("statusText"),
  indexProgress: document.getElementById("indexProgress"),
  indexProgressBar: document.getElementById("indexProgressBar"),
  indexProgressText: document.getElementById("indexProgressText"),
  indexProgressPercent: document.getElementById("indexProgressPercent"),
  chips: Array.from(document.querySelectorAll(".chip"))
};

const state = {
  sending: false,
  indexing: false,
  history: []
};

let indexingPollId = null;

function storageGet(keys) {
  return chrome.storage.local.get(keys);
}

function storageSet(value) {
  return chrome.storage.local.set(value);
}

async function fetchJson(path, options = {}, timeoutMs = REQUEST_TIMEOUT_MS.health) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      ...options,
      signal: controller.signal
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const message = data?.answer || data?.message || `HTTP ${response.status}`;
      const httpError = new Error(message);
      httpError.status = response.status;
      httpError.payload = data;
      throw httpError;
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Cererea a depășit timpul de așteptare.");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function normalizeSources(sources = []) {
  const seen = new Set();
  return sources
    .filter((source) => source && typeof source.url === "string" && source.url.trim())
    .map((source) => ({
      title: source.title?.trim() || "Sursă oficială",
      url: source.url.trim(),
      faculty_id: source.faculty_id || "uvt",
      page_type: source.page_type || "general",
      verified: Boolean(source.verified)
    }))
    .filter((source) => {
      if (seen.has(source.url)) {
        return false;
      }
      seen.add(source.url);
      return true;
    });
}

function normalizeHistoryEntry(entry) {
  if (!entry || !["user", "assistant"].includes(entry.role)) {
    return null;
  }

  const text = (entry.text || entry.content || "").trim();
  if (!text) {
    return null;
  }

  return {
    role: entry.role,
    text,
    sources: entry.role === "assistant" ? normalizeSources(entry.sources || []) : []
  };
}

function getHistoryStorageKey(facultyId) {
  return `chatHistory:${facultyId || "uvt"}`;
}

function buildHistoryPayload() {
  return state.history.map((entry) => ({ role: entry.role, content: entry.text }));
}

function appendHistory(role, text, sources = []) {
  const entry = normalizeHistoryEntry({ role, text, sources });
  if (!entry) {
    return;
  }
  state.history = [...state.history, entry].slice(-MAX_HISTORY_MESSAGES);
}

async function loadConversationHistory(facultyId) {
  const key = getHistoryStorageKey(facultyId);
  const stored = await storageGet([key]);
  const items = Array.isArray(stored[key]) ? stored[key] : [];
  state.history = items.map(normalizeHistoryEntry).filter(Boolean).slice(-MAX_HISTORY_MESSAGES);
  renderConversation();
}

async function saveConversationHistory(facultyId) {
  await storageSet({ [getHistoryStorageKey(facultyId)]: state.history });
}

function setBackendOnline(online) {
  refs.statusDot.classList.toggle("online", online);
}

function setStatus(kind, title, text) {
  refs.statusPanel.className = `status-panel status-${kind}`;
  refs.statusTitle.textContent = title;
  refs.statusText.textContent = text;
}

function updateControlState() {
  const disabled = state.sending || state.indexing;
  refs.send.disabled = disabled;
  refs.input.disabled = disabled;
  refs.faculty.disabled = disabled;
  refs.chips.forEach((chip) => {
    chip.disabled = disabled;
  });
}

function setBusy(busy) {
  state.sending = busy;
  updateControlState();
}

function setIndexingBusy(busy) {
  state.indexing = busy;
  updateControlState();
}

function clampProgress(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function renderIndexingProgress(indexing) {
  const running = Boolean(indexing?.running);
  setIndexingBusy(running);

  if (!running) {
    refs.indexProgress.hidden = true;
    refs.indexProgressBar.style.width = "0%";
    refs.indexProgressPercent.textContent = "0%";
    return;
  }

  const progress = clampProgress(indexing.progress);
  refs.indexProgress.hidden = false;
  refs.indexProgressBar.style.width = `${progress}%`;
  refs.indexProgressPercent.textContent = `${progress}%`;
  refs.indexProgressText.textContent = indexing.message || "Indexare în curs";
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

function handleIndexingStatus(indexing) {
  renderIndexingProgress(indexing);

  if (indexing?.running) {
    setBackendOnline(true);
    setStatus(
      "loading",
      "Indexare surse oficiale",
      indexing.message || "Backend-ul construiește indexul local complet."
    );
    startIndexingPoll();
    return true;
  }

  stopIndexingPoll();
  if (indexing?.error) {
    setStatus(
      "warning",
      "Indexarea a eșuat",
      indexing.error || "Verifică serviciile locale și logurile backend."
    );
  }
  return false;
}

async function checkIndexingStatus() {
  try {
    const data = await fetchJson("/indexing/status", {}, REQUEST_TIMEOUT_MS.health);
    const stillRunning = handleIndexingStatus(data?.indexing);
    if (!stillRunning) {
      await checkBackend();
    }
  } catch {
    stopIndexingPoll();
    setIndexingBusy(false);
    setBackendOnline(false);
    setStatus("error", "Backend indisponibil", "Nu pot citi progresul indexării de la 127.0.0.1:5000.");
  }
}

function resetMeta() {
  refs.confidenceBadge.textContent = "Încredere --";
  refs.confidenceBadge.className = "meta-badge muted";
  refs.verificationBadge.textContent = "Index local";
  refs.verificationBadge.className = "meta-badge muted";
  refs.metaLine.textContent = "Paginile oficiale specifice au prioritate față de paginile generale.";
}

function updateFacultyBadge() {
  const label = refs.faculty.options[refs.faculty.selectedIndex]?.text || "UVT";
  refs.facultyBadge.textContent = label.length > 26 ? `${label.slice(0, 26)}...` : label;
}

function clearLog() {
  refs.log.innerHTML = "";
  refs.log.appendChild(refs.emptyState);
}

function toggleEmptyState() {
  const hasMessages = refs.log.querySelectorAll(".msg").length > 0;
  refs.emptyState.hidden = hasMessages;
}

function scrollToBottom() {
  refs.log.scrollTop = refs.log.scrollHeight;
}

function createMessage(role, label, text) {
  const item = document.createElement("article");
  item.className = `msg ${role}`;

  const labelEl = document.createElement("div");
  labelEl.className = "msg-label";
  labelEl.textContent = label;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  item.append(labelEl, bubble);
  return item;
}

function addUserMessage(text) {
  refs.log.appendChild(createMessage("user", "Tu", text));
  toggleEmptyState();
  scrollToBottom();
}

function addBotMessage(text, sources = [], feedbackPayload = null) {
  refs.log.appendChild(createMessage("bot", "UVT Asist", text));

  const sourceBlock = createSourcesBlock(sources);
  if (sourceBlock) {
    refs.log.appendChild(sourceBlock);
  }

  const feedback = createFeedbackActions(feedbackPayload);
  if (feedback) {
    refs.log.appendChild(feedback);
  }

  toggleEmptyState();
  scrollToBottom();
}

function addLoadingMessage() {
  const item = document.createElement("article");
  item.id = "loadingMessage";
  item.className = "msg bot";

  const label = document.createElement("div");
  label.className = "msg-label";
  label.textContent = "UVT Asist";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.appendChild(createLoadingDots());

  item.append(label, bubble);
  refs.log.appendChild(item);
  toggleEmptyState();
  scrollToBottom();
}

function createLoadingDots() {
  const loading = document.createElement("div");
  loading.className = "loading";
  for (let index = 0; index < 3; index += 1) {
    loading.appendChild(document.createElement("span"));
  }
  return loading;
}

function removeLoadingMessage() {
  document.getElementById("loadingMessage")?.remove();
}

function formatSourceUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname.replace(/\/$/, "") || "/"}`;
  } catch {
    return url;
  }
}

function createSourcesBlock(sources) {
  if (!sources.length) {
    return null;
  }

  const block = document.createElement("section");
  block.className = "sources";

  const title = document.createElement("div");
  title.className = "sources-title";
  title.textContent = "Surse oficiale";
  block.appendChild(title);

  sources.forEach((source) => {
    const card = document.createElement("article");
    card.className = "source-card";

    const label = document.createElement("div");
    label.className = "source-label";
    label.textContent = source.title;

    const link = document.createElement("a");
    link.className = "source-link";
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = formatSourceUrl(source.url);
    link.title = source.url;

    card.append(label, link);
    block.appendChild(card);
  });

  return block;
}

async function postFeedback(payload) {
  await fetchJson("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }, REQUEST_TIMEOUT_MS.feedback);
}

function createFeedbackActions(payload) {
  if (!payload) {
    return null;
  }

  const block = document.createElement("div");
  block.className = "feedback-actions";

  const useful = document.createElement("button");
  useful.type = "button";
  useful.className = "feedback-btn";
  useful.textContent = "Util";

  const inaccurate = document.createElement("button");
  inaccurate.type = "button";
  inaccurate.className = "feedback-btn";
  inaccurate.textContent = "Inexact";

  const stateText = document.createElement("span");
  stateText.className = "feedback-state";

  async function sendFeedback(value) {
    useful.disabled = true;
    inaccurate.disabled = true;
    stateText.textContent = "Se salvează...";
    try {
      await postFeedback({ ...payload, feedback: value, created_at: new Date().toISOString() });
      stateText.textContent = "Salvat";
      setBackendOnline(true);
    } catch {
      stateText.textContent = "Netrimis";
      useful.disabled = false;
      inaccurate.disabled = false;
      setBackendOnline(false);
    }
  }

  useful.addEventListener("click", () => sendFeedback("positive"));
  inaccurate.addEventListener("click", () => sendFeedback("negative"));
  block.append(useful, inaccurate, stateText);
  return block;
}

function renderConversation() {
  clearLog();
  state.history.forEach((entry) => {
    if (entry.role === "user") {
      addUserMessage(entry.text);
    } else {
      addBotMessage(entry.text, entry.sources);
    }
  });
  toggleEmptyState();
}

function confidenceTone(confidence) {
  if (confidence === "high") {
    return "success";
  }
  if (confidence === "medium") {
    return "muted";
  }
  return "warning";
}

function updateResultMeta(data) {
  const confidence = data.confidence || "low";
  const score = Number.isFinite(data.confidence_score) ? data.confidence_score : 0;

  refs.confidenceBadge.textContent = `Încredere ${confidence} (${score})`;
  refs.confidenceBadge.className = `meta-badge ${confidenceTone(confidence)}`;

  refs.verificationBadge.textContent = data.live_verified ? "Verificat live" : "Index local";
  refs.verificationBadge.className = `meta-badge ${data.live_verified ? "success" : "muted"}`;

  const profile = data.query_profile || {};
  const evidence = data.evidence || {};
  const metaParts = [
    `Facultate: ${data.matched_faculty || "UVT"}`,
    `Intent: ${profile.intent || "general"}`
  ];
  if (Number.isFinite(evidence.source_count) && evidence.source_count > 0) {
    metaParts.push(`Surse: ${evidence.source_count}`);
  }
  if (Number.isFinite(evidence.verified_source_count) && evidence.verified_source_count > 0) {
    metaParts.push(`Verificate: ${evidence.verified_source_count}`);
  }
  if (profile.policy_question) {
    metaParts.push("Rutare: regulamente/metodologii");
  }
  if (data.retrieval_backend && data.retrieval_backend !== "qdrant") {
    metaParts.push(`Mod căutare: ${data.retrieval_backend}`);
  }
  if (data.generation_mode && data.generation_mode !== "ollama") {
    metaParts.push(`Mod răspuns: ${data.generation_mode}`);
  }
  if (data.confidence_reason) {
    metaParts.push(data.confidence_reason);
  }
  refs.metaLine.textContent = metaParts.join(" | ");
}

async function saveRecentQuestion(question) {
  const value = question.trim();
  if (!value) {
    return;
  }

  const stored = await storageGet([RECENT_QUESTIONS_KEY]);
  const recent = Array.isArray(stored[RECENT_QUESTIONS_KEY]) ? stored[RECENT_QUESTIONS_KEY] : [];
  const next = [value, ...recent.filter((item) => item !== value)].slice(0, 5);
  await storageSet({ [RECENT_QUESTIONS_KEY]: next });
  renderRecentQuestions(next);
}

async function loadRecentQuestions() {
  const stored = await storageGet([RECENT_QUESTIONS_KEY]);
  return Array.isArray(stored[RECENT_QUESTIONS_KEY]) ? stored[RECENT_QUESTIONS_KEY] : [];
}

function renderRecentQuestions(questions = []) {
  refs.recentQuestions.innerHTML = "";
  questions.forEach((question) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "recent-item";
    item.textContent = question;
    item.title = question;
    item.addEventListener("click", () => sendMessage(question));
    refs.recentQuestions.appendChild(item);
  });
}

function populateFaculties(faculties, selectedFacultyId) {
  refs.faculty.innerHTML = "";
  faculties.forEach((faculty) => {
    const option = document.createElement("option");
    option.value = faculty.id;
    option.textContent = faculty.name;
    refs.faculty.appendChild(option);
  });

  const ids = new Set(faculties.map((faculty) => faculty.id));
  refs.faculty.value = ids.has(selectedFacultyId) ? selectedFacultyId : "uvt";
  updateFacultyBadge();
}

async function loadFaculties() {
  const stored = await storageGet(["facultyId"]);
  const saved = stored.facultyId || "uvt";
  try {
    const data = await fetchJson("/faculties", {}, REQUEST_TIMEOUT_MS.faculties);
    populateFaculties(data.faculties || FALLBACK_FACULTIES, saved);
    setBackendOnline(true);
  } catch {
    populateFaculties(FALLBACK_FACULTIES, saved);
  }
}

function buildHealthMessages(data) {
  const checks = data?.checks || {};
  const ollama = data?.ollama || {};
  const index = data?.index || {};
  const vectorIndex = data?.vector_index || {};
  const statusReasons = Array.isArray(data?.status_reasons) ? data.status_reasons : [];
  const generationModel = ollama.generation_model || "qwen3:4b";
  const embeddingModel = ollama.embedding_model || "nomic-embed-text";
  const chunkCount = Number(index.chunk_count || 0);
  const vectorCount = Number(vectorIndex.points_count || 0);
  const messages = [];

  if (checks.ollama === false || ollama.available === false) {
    messages.push("Ollama nu răspunde. Pornește `ollama serve`.");
  } else {
    if (checks.generation_model === false || ollama.generation_model_available === false) {
      messages.push(`Modelul de generare lipsește. Rulează \`ollama pull ${generationModel}\`.`);
    }
    if (checks.embedding_model === false || ollama.embedding_model_available === false) {
      messages.push(`Modelul de embedding lipsește. Rulează \`ollama pull ${embeddingModel}\`.`);
    }
  }

  if (checks.json_index === false || index.exists === false || chunkCount === 0) {
    messages.push("Indexul local lipsește. Rulează `python backend/build_index.py`.");
  }

  if (checks.qdrant_index === false || vectorIndex.available === false || vectorCount === 0) {
    if (vectorIndex.available === false || vectorIndex.exists === false) {
      messages.push("Qdrant este indisponibil. Rulează `docker compose up -d qdrant`.");
    } else {
      messages.push("Qdrant nu are vectori indexați. Pornește Qdrant și reconstruiește indexul.");
    }
  }

  if (
    (checks.index_vector_count_match === false || (chunkCount > 0 && vectorCount > 0 && chunkCount !== vectorCount))
    && chunkCount > 0
    && vectorCount > 0
  ) {
    messages.push("Numărul de chunks din JSON nu corespunde cu punctele din Qdrant. Rulează `python backend/scripts/build_vector_index.py`.");
  }

  return messages.length ? messages : statusReasons;
}

async function checkBackend() {
  try {
    const data = await fetchJson("/health", {}, REQUEST_TIMEOUT_MS.health);
    const chunkCount = Number(data.index?.chunk_count || 0);
    const vectorCount = Number(data.vector_index?.points_count || 0);
    const builtAt = data.index?.built_at || "necunoscut";
    const generationModel = data.ollama?.generation_model || "Ollama";
    const embeddingModel = data.ollama?.embedding_model || "embedding local";
    const healthMessages = buildHealthMessages(data);
    setBackendOnline(true);
    if (handleIndexingStatus(data.indexing)) {
      refs.emptyText.textContent = "Indexarea oficială rulează. Întrebările vor fi disponibile după finalizare.";
      return true;
    }
    if (data.status === "ok") {
      setStatus(
        "idle",
        "Sistem pregătit",
        `Index oficial: ${chunkCount} fragmente. Vectori: ${vectorCount}. Model răspuns: ${generationModel}. Embedding: ${embeddingModel}. Build: ${builtAt}.`
      );
    } else {
      setStatus(
        "warning",
        "Sistem parțial disponibil",
        healthMessages.length ? healthMessages.join(" ") : "Unele componente locale nu sunt complet disponibile."
      );
    }
    refs.emptyText.textContent = "Exemple: orar, secretariat, admitere, burse, reguli despre cumularea burselor.";
    return true;
  } catch {
    stopIndexingPoll();
    setIndexingBusy(false);
    setBackendOnline(false);
    setStatus("error", "Backend indisponibil", "Pornește backend-ul Flask pe 127.0.0.1:5000 și reîncarcă popup-ul.");
    refs.emptyText.textContent = "Backend-ul nu răspunde. Extensia rămâne deschisă, dar nu poate genera răspunsuri.";
    return false;
  }
}

async function loadTheme() {
  const stored = await storageGet(["theme"]);
  applyTheme(stored.theme || "light");
}

function applyTheme(theme) {
  const dark = theme === "dark";
  document.body.classList.toggle("dark", dark);
  refs.themeToggle.textContent = dark ? "Light" : "Dark";
  refs.themeToggle.title = dark ? "Comută pe tema deschisă" : "Comută pe tema închisă";
}

async function toggleTheme() {
  const next = document.body.classList.contains("dark") ? "light" : "dark";
  applyTheme(next);
  await storageSet({ theme: next });
}

async function sendMessage(prefilledQuestion = null) {
  if (state.sending) {
    return;
  }

  if (state.indexing) {
    setStatus("loading", "Indexare surse oficiale", "Așteaptă finalizarea indexării înainte de a trimite o întrebare.");
    return;
  }

  const question = (prefilledQuestion ?? refs.input.value).trim();
  if (!question) {
    refs.input.focus();
    return;
  }

  await saveRecentQuestion(question);
  const stored = await storageGet(["facultyId"]);
  const facultyId = stored.facultyId || refs.faculty.value || "uvt";
  const history = buildHistoryPayload();

  setBusy(true);
  setStatus("loading", "Analizez întrebarea", "Caut semantic în Qdrant și verific doar sursele de top.");
  addUserMessage(question);
  refs.input.value = "";
  addLoadingMessage();

  try {
    const data = await fetchJson("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, faculty_id: facultyId, history })
    }, REQUEST_TIMEOUT_MS.chat);
    const sources = normalizeSources(data.sources || []);
    const answer = data.answer || "Nu există răspuns disponibil.";
    removeLoadingMessage();
    updateResultMeta(data);

    if (data.confidence === "low") {
      setStatus("warning", "Dovezi parțiale", "Răspunsul este limitat de sursele oficiale găsite.");
    } else {
      setStatus(
        "success",
        "Răspuns pregătit",
        data.live_verified ? "Sursele principale au fost reverificate live." : "Răspuns generat local cu Ollama din surse oficiale."
      );
    }

    addBotMessage(answer, sources, {
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
      sources
    });

    appendHistory("user", question);
    appendHistory("assistant", answer, sources);
    await saveConversationHistory(facultyId);
    setBackendOnline(true);
  } catch (error) {
    removeLoadingMessage();
    resetMeta();
    if (error.payload?.indexing) {
      handleIndexingStatus(error.payload.indexing);
      setBackendOnline(true);
      addBotMessage(error.payload.answer || "Indexarea este în curs. Încearcă după finalizare.");
      return;
    }
    setBackendOnline(false);
    setStatus("error", "Nu m-am putut conecta", error.message || "Verifică dacă backend-ul Flask rulează pe 127.0.0.1:5000.");
    addBotMessage("Nu m-am putut conecta la backend-ul Flask. Verifică serviciile locale și încearcă din nou.");
  } finally {
    setBusy(false);
  }
}

refs.faculty.addEventListener("change", async () => {
  await storageSet({ facultyId: refs.faculty.value });
  updateFacultyBadge();
  resetMeta();
  await loadConversationHistory(refs.faculty.value);
});

refs.send.addEventListener("click", () => sendMessage());
refs.themeToggle.addEventListener("click", toggleTheme);

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
  await loadTheme();
  resetMeta();
  await checkBackend();
  await loadFaculties();
  await loadConversationHistory(refs.faculty.value);
  renderRecentQuestions(await loadRecentQuestions());
})();
