const BACKEND_URL = "http://127.0.0.1:5000";
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

const MAX_HISTORY_MESSAGES = 10;
const RECENT_QUESTIONS_KEY = "recentQuestions";

const log = document.getElementById("log");
const input = document.getElementById("q");
const btn = document.getElementById("send");
const facultySelect = document.getElementById("faculty");
const facultyBadge = document.getElementById("facultyBadge");
const confidenceBadge = document.getElementById("confidenceBadge");
const verificationBadge = document.getElementById("verificationBadge");
const metaLine = document.getElementById("metaLine");
const emptyState = document.getElementById("emptyState");
const emptyText = document.getElementById("emptyText");
const statusDot = document.getElementById("statusDot");
const themeToggle = document.getElementById("themeToggle");
const recentQuestionsEl = document.getElementById("recentQuestions");
const quickActionChips = Array.from(document.querySelectorAll(".chip"));
const statusPanel = document.getElementById("statusPanel");
const statusTitle = document.getElementById("statusTitle");
const statusText = document.getElementById("statusText");

let isSending = false;
let conversationHistory = [];

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}

function toggleEmptyState() {
  const hasMessages = log.querySelectorAll(".msg").length > 0;
  if (emptyState) {
    emptyState.style.display = hasMessages ? "none" : "flex";
  }
}

function scrollToBottom() {
  log.scrollTop = log.scrollHeight;
}

function setStatus(online) {
  statusDot.classList.toggle("online", online);
}

function setSystemState(kind, title, text) {
  statusPanel.className = `status-panel status-${kind}`;
  statusTitle.textContent = title;
  statusText.textContent = text;
}

function resetMeta() {
  confidenceBadge.textContent = "Confidence --";
  confidenceBadge.className = "meta-badge muted";
  verificationBadge.textContent = "Index local";
  verificationBadge.className = "meta-badge muted";
  metaLine.textContent = "Raspunsurile vor prefera paginile oficiale specifice, nu homepage-uri generale.";
}

function getHistoryStorageKey(facultyId) {
  return `chatHistory:${facultyId || "uvt"}`;
}

function normalizeHistoryEntry(entry) {
  if (!entry || (entry.role !== "user" && entry.role !== "assistant")) {
    return null;
  }

  const text = typeof entry.text === "string"
    ? entry.text.trim()
    : typeof entry.content === "string"
      ? entry.content.trim()
      : "";

  if (!text) {
    return null;
  }

  return {
    role: entry.role,
    text,
    sources: entry.role === "assistant" ? normalizeSources(entry.sources || []) : []
  };
}

function normalizeConversationHistory(entries = []) {
  if (!Array.isArray(entries)) {
    return [];
  }

  return entries
    .map(normalizeHistoryEntry)
    .filter(Boolean)
    .slice(-MAX_HISTORY_MESSAGES);
}

function buildHistoryPayload() {
  return conversationHistory.map((entry) => ({
    role: entry.role,
    content: entry.text
  }));
}

function appendHistory(role, text, sources = []) {
  const normalized = normalizeHistoryEntry({ role, text, sources });
  if (!normalized) {
    return;
  }

  conversationHistory = [...conversationHistory, normalized].slice(-MAX_HISTORY_MESSAGES);
}

function renderConversationHistory() {
  log.innerHTML = "";
  log.appendChild(emptyState);

  conversationHistory.forEach((entry) => {
    if (entry.role === "user") {
      addUserMessage(entry.text);
      return;
    }

    addBotMessage(entry.text, entry.sources);
  });

  toggleEmptyState();
}

async function loadConversationHistory(facultyId) {
  const historyKey = getHistoryStorageKey(facultyId);
  const stored = await chrome.storage.local.get([historyKey]);
  conversationHistory = normalizeConversationHistory(stored[historyKey] || []);
  renderConversationHistory();
}

async function saveConversationHistory(facultyId) {
  const historyKey = getHistoryStorageKey(facultyId);
  await chrome.storage.local.set({
    [historyKey]: conversationHistory
  });
}

function setSendingState(sending) {
  isSending = sending;
  btn.disabled = sending;
  input.disabled = sending;
  facultySelect.disabled = sending;

  quickActionChips.forEach((chip) => {
    chip.disabled = sending;
  });
}

async function loadTheme() {
  const stored = await chrome.storage.local.get(["theme"]);
  applyTheme(stored.theme || "light");
}

function applyTheme(theme) {
  const isDark = theme === "dark";
  document.body.classList.toggle("dark", isDark);
  themeToggle.textContent = isDark ? "L" : "D";
  themeToggle.title = isDark ? "Comuta pe tema deschisa" : "Comuta pe tema inchisa";
  themeToggle.setAttribute("aria-label", themeToggle.title);
}

async function toggleTheme() {
  const nextTheme = document.body.classList.contains("dark") ? "light" : "dark";
  applyTheme(nextTheme);
  await chrome.storage.local.set({ theme: nextTheme });
}

function updateFacultyBadge() {
  const text = facultySelect.options[facultySelect.selectedIndex]?.text || "UVT";
  facultyBadge.textContent = text.length > 22 ? `${text.slice(0, 22)}...` : text;
}

function createMessage(type, label, html) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${type}`;

  const name = document.createElement("div");
  name.className = "msg-label";
  name.textContent = label;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = html;

  wrap.appendChild(name);
  wrap.appendChild(bubble);
  return wrap;
}

function normalizeSources(sources = []) {
  const seen = new Set();

  return sources
    .filter((source) => source && typeof source.url === "string" && source.url.trim())
    .map((source) => ({
      title: typeof source.title === "string" && source.title.trim()
        ? source.title.trim()
        : "Sursa oficiala",
      url: source.url.trim(),
      faculty_id: typeof source.faculty_id === "string" ? source.faculty_id : "uvt",
      page_type: typeof source.page_type === "string" ? source.page_type : "general",
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

function formatSourceUrl(url) {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname.replace(/\/$/, "") || "/";
    return `${parsed.hostname}${path}`;
  } catch (error) {
    return url;
  }
}

function labelPageType(pageType) {
  const labels = {
    orar: "Orar",
    burse: "Burse",
    contact: "Contact",
    admitere: "Admitere",
    regulamente: "Regulamente",
    studenti: "Studenti",
    general: "General"
  };
  return labels[pageType] || "General";
}

function createSources(sources) {
  if (!sources || !sources.length) {
    return null;
  }

  const block = document.createElement("div");
  block.className = "sources";

  const title = document.createElement("div");
  title.className = "sources-title";
  title.textContent = "Surse oficiale";
  block.appendChild(title);

  sources.forEach((source) => {
    const card = document.createElement("div");
    card.className = "source-card";

    const header = document.createElement("div");
    header.className = "source-header";

    const label = document.createElement("div");
    label.className = "source-label";
    label.textContent = source.title || "Sursa oficiala";

    const pills = document.createElement("div");
    pills.className = "source-pills";

    const pageTypePill = document.createElement("span");
    pageTypePill.className = "source-pill";
    pageTypePill.textContent = labelPageType(source.page_type);
    pills.appendChild(pageTypePill);

    const facultyPill = document.createElement("span");
    facultyPill.className = "source-pill";
    facultyPill.textContent = (source.faculty_id || "uvt").toUpperCase();
    pills.appendChild(facultyPill);

    if (source.verified) {
      const verifiedPill = document.createElement("span");
      verifiedPill.className = "source-pill verified";
      verifiedPill.textContent = "Live";
      pills.appendChild(verifiedPill);
    }

    header.appendChild(label);
    header.appendChild(pills);

    const link = document.createElement("a");
    link.className = "source-link";
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = formatSourceUrl(source.url);
    link.title = source.url;

    card.appendChild(header);
    card.appendChild(link);
    block.appendChild(card);
  });

  return block;
}

async function postFeedback(payload) {
  const response = await fetch(`${BACKEND_URL}/feedback`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
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

  const label = document.createElement("span");
  label.className = "feedback-label";
  label.textContent = "Feedback";

  const positiveBtn = document.createElement("button");
  positiveBtn.type = "button";
  positiveBtn.className = "feedback-btn";
  positiveBtn.textContent = "Util";

  const negativeBtn = document.createElement("button");
  negativeBtn.type = "button";
  negativeBtn.className = "feedback-btn";
  negativeBtn.textContent = "Inexact";

  const state = document.createElement("span");
  state.className = "feedback-state";

  async function sendFeedback(value) {
    positiveBtn.disabled = true;
    negativeBtn.disabled = true;
    state.textContent = "...";

    try {
      await postFeedback({
        ...payload,
        feedback: value,
        created_at: new Date().toISOString()
      });
      state.textContent = "Salvat";
      setStatus(true);
    } catch (error) {
      state.textContent = "Netrimis";
      positiveBtn.disabled = false;
      negativeBtn.disabled = false;
      setStatus(false);
    }
  }

  positiveBtn.addEventListener("click", () => {
    sendFeedback("positive");
  });

  negativeBtn.addEventListener("click", () => {
    sendFeedback("negative");
  });

  block.appendChild(label);
  block.appendChild(positiveBtn);
  block.appendChild(negativeBtn);
  block.appendChild(state);
  return block;
}

function addUserMessage(text) {
  const msg = createMessage("user", "Tu", esc(text));
  log.appendChild(msg);
  toggleEmptyState();
  scrollToBottom();
}

function addBotMessage(text, sources = [], feedbackPayload = null) {
  const msg = createMessage("bot", "UVT Asist", esc(text));
  log.appendChild(msg);

  const sourceBlock = createSources(sources);
  if (sourceBlock) {
    log.appendChild(sourceBlock);
  }

  const feedbackBlock = createFeedbackActions(feedbackPayload);
  if (feedbackBlock) {
    log.appendChild(feedbackBlock);
  }

  toggleEmptyState();
  scrollToBottom();
}

function addLoadingMessage() {
  const msg = createMessage(
    "bot",
    "UVT Asist",
    "<div class=\"loading\"><span></span><span></span><span></span></div>"
  );
  msg.id = "loadingMessage";
  log.appendChild(msg);
  toggleEmptyState();
  scrollToBottom();
}

function removeLoadingMessage() {
  const node = document.getElementById("loadingMessage");
  if (node) {
    node.remove();
  }
}

function formatConfidence(confidence, confidenceScore) {
  const label = typeof confidence === "string" && confidence.trim()
    ? confidence.trim().toLowerCase()
    : "unknown";
  const title = label.charAt(0).toUpperCase() + label.slice(1);
  return `Confidence ${title} ${typeof confidenceScore === "number" ? `(${confidenceScore})` : ""}`.trim();
}

function confidenceBadgeTone(confidence) {
  if (confidence === "high") {
    return "success";
  }
  if (confidence === "medium") {
    return "muted";
  }
  return "warning";
}

function formatIntent(intent) {
  const labels = {
    orar: "orar",
    burse: "burse",
    contact: "contact",
    admitere: "admitere",
    regulamente: "regulamente",
    studenti: "studenti",
    general: "general"
  };
  return labels[intent] || "general";
}

function updateResultMeta(data) {
  const confidence = data.confidence || "low";
  const confidenceScore = typeof data.confidence_score === "number" ? data.confidence_score : 0;
  confidenceBadge.textContent = formatConfidence(confidence, confidenceScore);
  confidenceBadge.className = `meta-badge ${confidenceBadgeTone(confidence)}`;

  if (data.live_verified) {
    verificationBadge.textContent = "Verificare live";
    verificationBadge.className = "meta-badge success";
  } else {
    verificationBadge.textContent = "Index local";
    verificationBadge.className = "meta-badge muted";
  }

  const metaParts = [];
  const queryProfile = data.query_profile || {};
  metaParts.push(`Facultate: ${data.matched_faculty || "UVT"}`);
  metaParts.push(`Intent: ${formatIntent(queryProfile.intent)}`);

  if (queryProfile.policy_question) {
    metaParts.push("Rutare: reguli/metodologii");
  }

  if (data.confidence_reason) {
    metaParts.push(data.confidence_reason);
  }

  metaLine.textContent = metaParts.join(" • ");
}

async function saveRecentQuestion(question) {
  const normalizedQuestion = String(question || "").trim();
  if (!normalizedQuestion) {
    return;
  }

  const stored = await chrome.storage.local.get([RECENT_QUESTIONS_KEY]);
  const recent = Array.isArray(stored[RECENT_QUESTIONS_KEY]) ? stored[RECENT_QUESTIONS_KEY] : [];
  const next = [normalizedQuestion, ...recent.filter((item) => item !== normalizedQuestion)].slice(0, 5);
  await chrome.storage.local.set({ [RECENT_QUESTIONS_KEY]: next });
  renderRecentQuestions(next);
}

async function loadRecentQuestions() {
  const stored = await chrome.storage.local.get([RECENT_QUESTIONS_KEY]);
  return Array.isArray(stored[RECENT_QUESTIONS_KEY]) ? stored[RECENT_QUESTIONS_KEY] : [];
}

function renderRecentQuestions(questions = []) {
  if (!recentQuestionsEl) {
    return;
  }

  recentQuestionsEl.innerHTML = "";

  questions.forEach((question) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "recent-item";
    item.textContent = question;
    item.title = question;
    item.addEventListener("click", () => {
      input.value = question;
      sendMessage(question);
    });
    recentQuestionsEl.appendChild(item);
  });
}

async function checkBackend() {
  try {
    const response = await fetch(`${BACKEND_URL}/health`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const chunkCount = data.index?.chunk_count || 0;
    const builtAt = data.index?.built_at || "necunoscut";
    setStatus(true);
    setSystemState(
      "idle",
      "Backend disponibil",
      `Index local activ (${chunkCount} fragmente). Ultima build: ${builtAt}.`
    );
    emptyText.textContent = "Exemple: unde gasesc orarul, program secretariat, admitere, burse, reguli pentru doua burse";
    return true;
  } catch (error) {
    setStatus(false);
    setSystemState(
      "error",
      "Backend indisponibil",
      "Porneste backend-ul Flask si verifica GEMINI_API_KEY daca vrei raspuns complet."
    );
    emptyText.textContent = "Backend-ul nu raspunde momentan. Porneste serverul Flask pentru a folosi extensia.";
    return false;
  }
}

function populateFaculties(faculties, selectedFacultyId) {
  facultySelect.innerHTML = "";

  faculties.forEach((faculty) => {
    const opt = document.createElement("option");
    opt.value = faculty.id;
    opt.textContent = faculty.name;
    facultySelect.appendChild(opt);
  });

  const availableIds = new Set(faculties.map((faculty) => faculty.id));
  facultySelect.value = availableIds.has(selectedFacultyId) ? selectedFacultyId : "uvt";
  updateFacultyBadge();
}

async function loadFaculties() {
  const stored = await chrome.storage.local.get(["facultyId"]);
  const saved = stored.facultyId || "uvt";

  try {
    const response = await fetch(`${BACKEND_URL}/faculties`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    populateFaculties(data.faculties || FALLBACK_FACULTIES, saved);
    setStatus(true);
  } catch (error) {
    populateFaculties(FALLBACK_FACULTIES, saved);
  }
}

facultySelect.addEventListener("change", async () => {
  await chrome.storage.local.set({ facultyId: facultySelect.value });
  updateFacultyBadge();
  resetMeta();
  await loadConversationHistory(facultySelect.value);
});

async function sendMessage(prefilledQuestion = null) {
  if (isSending) {
    return;
  }

  const question = (prefilledQuestion ?? input.value).trim();
  if (!question) {
    return;
  }

  await saveRecentQuestion(question);
  setSendingState(true);
  setSystemState("loading", "Analizez intrebarea", "Rulez rutarea pe indexul local si verific doar cele mai bune surse.");
  addUserMessage(question);
  input.value = "";
  addLoadingMessage();

  try {
    const stored = await chrome.storage.local.get(["facultyId"]);
    const facultyId = stored.facultyId || facultySelect.value || "uvt";
    const history = buildHistoryPayload();

    const response = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        question,
        faculty_id: facultyId,
        history
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const sources = normalizeSources(data.sources || []);
    const answer = data.answer || "Nu exista raspuns disponibil.";
    const confidence = data.confidence || "low";

    removeLoadingMessage();
    updateResultMeta(data);

    if (confidence === "low") {
      setSystemState(
        "warning",
        "Dovezi partiale",
        "Am gasit doar potriviri limitate. Verifica in special sursele oficiale afisate."
      );
    } else {
      setSystemState(
        "success",
        "Raspuns pregatit",
        data.live_verified
          ? "Sursele de top au fost reverificate live inainte de generarea raspunsului."
          : "Raspunsul a fost generat din indexul local oficial."
      );
    }

    addBotMessage(answer, sources, {
      source: "popup",
      question,
      answer,
      faculty_id: facultyId,
      matched_faculty: data.matched_faculty || "UVT",
      confidence: confidence,
      confidence_score: data.confidence_score || 0,
      live_verified: Boolean(data.live_verified),
      sources
    });

    appendHistory("user", question);
    appendHistory("assistant", answer, sources);
    await saveConversationHistory(facultyId);
    setStatus(true);
  } catch (error) {
    removeLoadingMessage();
    resetMeta();
    setSystemState(
      "error",
      "Nu m-am putut conecta la backend",
      "Porneste backend-ul Flask si reincarca extensia daca problema persista."
    );
    addBotMessage("Nu m-am putut conecta la backend-ul Flask.");
    setStatus(false);
  } finally {
    setSendingState(false);
  }
}

btn.addEventListener("click", () => {
  sendMessage();
});

themeToggle.addEventListener("click", toggleTheme);

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

quickActionChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    input.value = chip.dataset.q;
    sendMessage();
  });
});

(async function init() {
  await loadTheme();
  resetMeta();
  await checkBackend();
  await loadFaculties();
  await loadConversationHistory(facultySelect.value);
  renderRecentQuestions(await loadRecentQuestions());
}());
