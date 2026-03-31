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
const meta = document.getElementById("meta");
const emptyState = document.getElementById("emptyState");
const statusDot = document.getElementById("statusDot");
const themeToggle = document.getElementById("themeToggle");
const recentQuestionsEl = document.getElementById("recentQuestions");
const quickActionChips = Array.from(document.querySelectorAll(".chip"));

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
      url: source.url.trim()
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

function createSources(sources) {
  if (!sources || !sources.length) {
    return null;
  }

  const block = document.createElement("div");
  block.className = "sources";

  const title = document.createElement("div");
  title.className = "sources-title";
  title.textContent = "Surse";
  block.appendChild(title);

  sources.forEach((source) => {
    const card = document.createElement("div");
    card.className = "source-card";

    const label = document.createElement("div");
    label.className = "source-label";
    label.textContent = source.title || "Sursa oficiala";

    const link = document.createElement("a");
    link.className = "source-link";
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = formatSourceUrl(source.url);
    link.title = source.url;

    card.appendChild(label);
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

function formatConfidence(confidence) {
  const value = typeof confidence === "string" && confidence.trim()
    ? confidence.trim().toLowerCase()
    : "unknown";

  return value.charAt(0).toUpperCase() + value.slice(1);
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
    if (response.ok) {
      setStatus(true);
      return true;
    }
  } catch (error) {
  }

  setStatus(false);
  return false;
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
  meta.textContent = "";
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
    const metaParts = [
      `Facultate: ${data.matched_faculty || "UVT"}`,
      `Confidence: ${formatConfidence(data.confidence)}`
    ];

    if (data.live_verified) {
      metaParts.push("Live verified");
    }

    removeLoadingMessage();
    meta.textContent = metaParts.join(" \u2022 ");
    addBotMessage(answer, sources, {
      source: "popup",
      question,
      answer,
      faculty_id: facultyId,
      matched_faculty: data.matched_faculty || "UVT",
      confidence: data.confidence || "unknown",
      live_verified: Boolean(data.live_verified),
      sources
    });

    appendHistory("user", question);
    appendHistory("assistant", answer, sources);
    await saveConversationHistory(facultyId);
    setStatus(true);
  } catch (error) {
    removeLoadingMessage();
    meta.textContent = "Backend indisponibil";
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
  if (event.key === "Enter") {
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
  await checkBackend();
  await loadFaculties();
  await loadConversationHistory(facultySelect.value);
  renderRecentQuestions(await loadRecentQuestions());
}());
