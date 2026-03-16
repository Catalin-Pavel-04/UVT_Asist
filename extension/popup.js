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
const INTENT_LABELS = {
  general: "general",
  orar: "schedule",
  burse: "scholarships",
  contact: "contact",
  admitere: "admission",
  cazare: "accommodation",
  mobilitati: "mobility",
  regulamente: "regulations"
};

const log = document.getElementById("log");
const input = document.getElementById("q");
const btn = document.getElementById("send");
const facultySelect = document.getElementById("faculty");
const facultyBadge = document.getElementById("facultyBadge");
const meta = document.getElementById("meta");
const emptyState = document.getElementById("emptyState");

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

function setMeta(text) {
  meta.textContent = text || "";
}

function formatIntent(intent) {
  return INTENT_LABELS[intent] || intent || "general";
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

function createSources(sourceDetails = [], urls = []) {
  const normalizedSources = sourceDetails.length
    ? sourceDetails
    : urls.map((url) => ({ title: "", url, snippet: "" }));

  if (!normalizedSources.length) {
    return null;
  }

  const container = document.createElement("div");
  container.className = "sources";

  const title = document.createElement("div");
  title.className = "sources-title";
  title.textContent = "Sources";
  container.appendChild(title);

  normalizedSources.forEach((source) => {
    const card = document.createElement("div");
    card.className = "source-card";

    if (source.title) {
      const name = document.createElement("div");
      name.className = "source-name";
      name.textContent = source.title;
      card.appendChild(name);
    }

    if (source.snippet) {
      const snippet = document.createElement("div");
      snippet.className = "source-snippet";
      snippet.textContent = source.snippet;
      card.appendChild(snippet);
    }

    const link = document.createElement("a");
    link.className = "source-link";
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = source.url;
    card.appendChild(link);

    container.appendChild(card);
  });

  return container;
}

function createFeedback(feedbackPayload) {
  if (!feedbackPayload) {
    return null;
  }

  const container = document.createElement("div");
  container.className = "feedback";

  const usefulButton = document.createElement("button");
  usefulButton.type = "button";
  usefulButton.textContent = "Useful";

  const notUsefulButton = document.createElement("button");
  notUsefulButton.type = "button";
  notUsefulButton.textContent = "Not useful";

  usefulButton.addEventListener("click", () => {
    sendFeedback({ ...feedbackPayload, vote: "up" });
    usefulButton.disabled = true;
    notUsefulButton.disabled = true;
  });

  notUsefulButton.addEventListener("click", () => {
    sendFeedback({ ...feedbackPayload, vote: "down" });
    usefulButton.disabled = true;
    notUsefulButton.disabled = true;
  });

  container.appendChild(usefulButton);
  container.appendChild(notUsefulButton);
  return container;
}

function addUserMessage(text) {
  const message = createMessage("user", "You", esc(text));
  log.appendChild(message);
  toggleEmptyState();
  scrollToBottom();
}

function addBotMessage(text, sourceDetails = [], urls = [], feedbackPayload = null) {
  const message = createMessage("bot", "UVT Asist", esc(text));
  log.appendChild(message);

  const sourceBlock = createSources(sourceDetails, urls);
  if (sourceBlock) {
    log.appendChild(sourceBlock);
  }

  const feedbackBlock = createFeedback(feedbackPayload);
  if (feedbackBlock) {
    log.appendChild(feedbackBlock);
  }

  toggleEmptyState();
  scrollToBottom();
}

function addLoadingMessage() {
  const message = createMessage(
    "bot",
    "UVT Asist",
    "<div class=\"loading\"><span></span><span></span><span></span></div>"
  );
  message.id = "loadingMessage";
  log.appendChild(message);
  toggleEmptyState();
  scrollToBottom();
}

function removeLoadingMessage() {
  const loading = document.getElementById("loadingMessage");
  if (loading) {
    loading.remove();
  }
}

async function sendFeedback(payload) {
  try {
    await fetch(`${BACKEND_URL}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (error) {
    console.debug("Feedback request failed", error);
  }
}

async function getCurrentTabUrl() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0]?.url || "";
  } catch (error) {
    return "";
  }
}

async function ensureSessionId() {
  const stored = await chrome.storage.local.get(["sessionId"]);
  if (stored.sessionId) {
    return stored.sessionId;
  }

  const sessionId = crypto.randomUUID();
  await chrome.storage.local.set({ sessionId });
  return sessionId;
}

function updateFacultyBadge() {
  const label = facultySelect.options[facultySelect.selectedIndex]?.text || "UVT";
  facultyBadge.textContent = label.length > 24 ? `${label.slice(0, 24)}...` : label;
}

function populateFaculties(faculties, selectedFacultyId) {
  facultySelect.innerHTML = "";
  faculties.forEach((faculty) => {
    const option = document.createElement("option");
    option.value = faculty.id;
    option.textContent = faculty.name;
    facultySelect.appendChild(option);
  });
  facultySelect.value = selectedFacultyId;
  updateFacultyBadge();
}

async function loadFaculties() {
  const stored = await chrome.storage.local.get(["facultyId"]);
  const selectedFacultyId = stored.facultyId || "uvt";

  try {
    const response = await fetch(`${BACKEND_URL}/faculties`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    populateFaculties(data.faculties || FALLBACK_FACULTIES, selectedFacultyId);
  } catch (error) {
    populateFaculties(FALLBACK_FACULTIES, selectedFacultyId);
    setMeta("Faculty list loaded from local fallback.");
  }
}

facultySelect.addEventListener("change", async () => {
  await chrome.storage.local.set({ facultyId: facultySelect.value });
  updateFacultyBadge();
});

async function sendMessage(prefilledQuestion = null) {
  const question = (prefilledQuestion ?? input.value).trim();
  if (!question) {
    return;
  }

  btn.disabled = true;
  addUserMessage(question);
  input.value = "";
  addLoadingMessage();

  try {
    const sessionId = await ensureSessionId();
    const stored = await chrome.storage.local.get(["facultyId"]);
    const facultyId = stored.facultyId || facultySelect.value || "uvt";
    const currentUrl = await getCurrentTabUrl();

    const response = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        faculty_id: facultyId,
        current_url: currentUrl,
        session_id: sessionId
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    removeLoadingMessage();

    if (data.session_id && data.session_id !== sessionId) {
      await chrome.storage.local.set({ sessionId: data.session_id });
    }

    const metaParts = [];
    metaParts.push(`Intent: ${formatIntent(data.intent)}`);
    metaParts.push(`Faculty: ${data.matched_faculty || "UVT"}`);
    setMeta(metaParts.join(" | "));

    addBotMessage(
      data.answer || "No answer available.",
      data.source_details || [],
      data.sources || [],
      {
        question,
        faculty_id: facultyId,
        current_url: currentUrl,
        session_id: data.session_id || sessionId,
        intent: data.intent || "general"
      }
    );
  } catch (error) {
    removeLoadingMessage();
    setMeta("Backend unavailable");
    addBotMessage("Could not connect to the Flask backend.");
  } finally {
    btn.disabled = false;
  }
}

btn.addEventListener("click", () => {
  sendMessage();
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    sendMessage();
  }
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    sendMessage(chip.dataset.q || "");
  });
});

loadFaculties();
toggleEmptyState();
