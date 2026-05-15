const BACKEND_URL = "http://127.0.0.1:5000";
const RECENT_QUESTIONS_KEY = "recentQuestions";
const MAX_HISTORY_MESSAGES = 10;

const FALLBACK_FACULTIES = [
  { id: "uvt", name: "UVT (general)" },
  { id: "arte", name: "Facultatea de Arte si Design" },
  { id: "cbg", name: "Facultatea de Chimie, Biologie, Geografie" },
  { id: "drept", name: "Facultatea de Drept" },
  { id: "feaa", name: "Facultatea de Economie si de Administrare a Afacerilor" },
  { id: "sport", name: "Facultatea de Educatie Fizica si Sport" },
  { id: "ffm", name: "Facultatea de Fizica si Matematica" },
  { id: "info", name: "Facultatea de Informatica" },
  { id: "fmt", name: "Facultatea de Muzica si Teatru" },
  { id: "lift", name: "Facultatea de Litere, Istorie, Filosofie si Teologie" },
  { id: "fsas", name: "Facultatea de Sociologie si Asistenta Sociala" },
  { id: "fpse", name: "Facultatea de Psihologie si Stiinte ale Educatiei" },
  { id: "fsgc", name: "Facultatea de Stiinte ale Guvernarii si Comunicarii" }
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
  chips: Array.from(document.querySelectorAll(".chip"))
};

const state = {
  sending: false,
  history: []
};

function storageGet(keys) {
  return chrome.storage.local.get(keys);
}

function storageSet(value) {
  return chrome.storage.local.set(value);
}

function normalizeSources(sources = []) {
  const seen = new Set();
  return sources
    .filter((source) => source && typeof source.url === "string" && source.url.trim())
    .map((source) => ({
      title: source.title?.trim() || "Sursa oficiala",
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

function setBusy(busy) {
  state.sending = busy;
  refs.send.disabled = busy;
  refs.input.disabled = busy;
  refs.faculty.disabled = busy;
  refs.chips.forEach((chip) => {
    chip.disabled = busy;
  });
}

function resetMeta() {
  refs.confidenceBadge.textContent = "Confidence --";
  refs.confidenceBadge.className = "meta-badge muted";
  refs.verificationBadge.textContent = "Index local";
  refs.verificationBadge.className = "meta-badge muted";
  refs.metaLine.textContent = "Paginile oficiale specifice au prioritate fata de paginile generale.";
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
  const response = await fetch(`${BACKEND_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
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
    stateText.textContent = "Se salveaza...";
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

  refs.confidenceBadge.textContent = `Confidence ${confidence} (${score})`;
  refs.confidenceBadge.className = `meta-badge ${confidenceTone(confidence)}`;

  refs.verificationBadge.textContent = data.live_verified ? "Verificat live" : "Index local";
  refs.verificationBadge.className = `meta-badge ${data.live_verified ? "success" : "muted"}`;

  const profile = data.query_profile || {};
  const metaParts = [
    `Facultate: ${data.matched_faculty || "UVT"}`,
    `Intent: ${profile.intent || "general"}`
  ];
  if (profile.policy_question) {
    metaParts.push("Rutare: regulamente/metodologii");
  }
  if (data.retrieval_backend) {
    metaParts.push(`Retrieval: ${data.retrieval_backend}`);
  }
  if (data.generation_mode) {
    metaParts.push(`Generare: ${data.generation_mode}`);
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
    const response = await fetch(`${BACKEND_URL}/faculties`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    populateFaculties(data.faculties || FALLBACK_FACULTIES, saved);
    setBackendOnline(true);
  } catch {
    populateFaculties(FALLBACK_FACULTIES, saved);
  }
}

async function checkBackend() {
  try {
    const response = await fetch(`${BACKEND_URL}/health`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    const chunkCount = data.index?.chunk_count || 0;
    const vectorCount = data.vector_index?.points_count || 0;
    const builtAt = data.index?.built_at || "necunoscut";
    const generationModel = data.ollama?.generation_model || "Ollama";
    const embeddingModel = data.ollama?.embedding_model || "embedding local";
    setBackendOnline(true);
    setStatus(
      "idle",
      "Backend disponibil",
      `Qdrant: ${vectorCount} vectori. JSON: ${chunkCount} fragmente. Model: ${generationModel}. Embedding: ${embeddingModel}. Build: ${builtAt}.`
    );
    refs.emptyText.textContent = "Exemple: orar, secretariat, admitere, burse, reguli despre cumularea burselor.";
    return true;
  } catch {
    setBackendOnline(false);
    setStatus("error", "Backend indisponibil", "Porneste backend-ul Flask pe 127.0.0.1:5000 si reincarca popup-ul.");
    refs.emptyText.textContent = "Backend-ul nu raspunde. Extensia ramane deschisa, dar nu poate genera raspunsuri.";
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
  refs.themeToggle.title = dark ? "Comuta pe tema deschisa" : "Comuta pe tema inchisa";
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
  setStatus("loading", "Analizez intrebarea", "Caut semantic in Qdrant si verific doar sursele de top.");
  addUserMessage(question);
  refs.input.value = "";
  addLoadingMessage();

  try {
    const response = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, faculty_id: facultyId, history })
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const sources = normalizeSources(data.sources || []);
    const answer = data.answer || "Nu exista raspuns disponibil.";
    removeLoadingMessage();
    updateResultMeta(data);

    if (data.confidence === "low") {
      setStatus("warning", "Dovezi partiale", "Raspunsul este limitat de sursele oficiale gasite.");
    } else {
      setStatus(
        "success",
        "Raspuns pregatit",
        data.live_verified ? "Sursele principale au fost reverificate live." : "Raspuns generat local cu Ollama din surse oficiale."
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
  } catch {
    removeLoadingMessage();
    resetMeta();
    setBackendOnline(false);
    setStatus("error", "Nu m-am putut conecta", "Verifica daca backend-ul Flask ruleaza pe 127.0.0.1:5000.");
    addBotMessage("Nu m-am putut conecta la backend-ul Flask. Porneste serverul si incearca din nou.");
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
