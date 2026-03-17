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

const log = document.getElementById("log");
const input = document.getElementById("q");
const btn = document.getElementById("send");
const facultySelect = document.getElementById("faculty");
const facultyBadge = document.getElementById("facultyBadge");
const meta = document.getElementById("meta");
const emptyState = document.getElementById("emptyState");
const statusDot = document.getElementById("statusDot");
const themeToggle = document.getElementById("themeToggle");

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

function createSources(sources = []) {
  const normalizedSources = normalizeSources(sources);
  if (!normalizedSources.length) {
    return null;
  }

  const block = document.createElement("div");
  block.className = "sources";

  const title = document.createElement("div");
  title.className = "sources-title";
  title.textContent = "Surse";
  block.appendChild(title);

  normalizedSources.forEach((source) => {
    const card = document.createElement("div");
    card.className = "source-card";

    const label = document.createElement("div");
    label.className = "source-label";
    label.textContent = source.title;
    card.appendChild(label);

    const link = document.createElement("a");
    link.className = "source-link";
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = source.url;
    card.appendChild(link);

    block.appendChild(card);
  });

  return block;
}

function addUserMessage(text) {
  const msg = createMessage("user", "Tu", esc(text));
  log.appendChild(msg);
  toggleEmptyState();
  scrollToBottom();
}

function addBotMessage(text, sources = []) {
  const msg = createMessage("bot", "UVT Asist", esc(text));
  log.appendChild(msg);

  const sourceBlock = createSources(sources);
  if (sourceBlock) {
    log.appendChild(sourceBlock);
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
  } catch (error) {
    populateFaculties(FALLBACK_FACULTIES, saved);
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
    const stored = await chrome.storage.local.get(["facultyId"]);
    const facultyId = stored.facultyId || facultySelect.value || "uvt";

    const response = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        question,
        faculty_id: facultyId
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const sources = normalizeSources(data.sources || []);
    const metaParts = [];

    if (data.matched_faculty) {
      metaParts.push(`Facultate: ${data.matched_faculty}`);
    }
    if (sources.length) {
      metaParts.push(`Surse: ${sources.length}`);
    }

    removeLoadingMessage();
    meta.textContent = metaParts.join(" | ");
    addBotMessage(data.answer || "Nu exista raspuns disponibil.", sources);
    setStatus(true);
  } catch (error) {
    removeLoadingMessage();
    meta.textContent = "Backend indisponibil";
    addBotMessage("Nu m-am putut conecta la backend-ul Flask.");
    setStatus(false);
  } finally {
    btn.disabled = false;
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

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    input.value = chip.dataset.q;
    sendMessage();
  });
});

(async function init() {
  await loadTheme();
  await checkBackend();
  await loadFaculties();
  toggleEmptyState();
}());
