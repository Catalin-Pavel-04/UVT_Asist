const BACKEND_URL = "http://127.0.0.1:5000";
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
const INTENT_LABELS = {
  general: "general",
  orar: "orar",
  burse: "burse",
  contact: "contact",
  admitere: "admitere",
  cazare: "cazare",
  mobilitati: "mobilități",
  regulamente: "regulamente"
};

const log = document.getElementById("log");
const input = document.getElementById("q");
const btn = document.getElementById("send");
const facultySelect = document.getElementById("faculty");
const meta = document.getElementById("meta");

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}

function setMeta(text) {
  meta.textContent = text || "";
}

function formatIntent(intent) {
  return INTENT_LABELS[intent] || intent || "general";
}

function addMsg(who, html, sources = [], feedbackPayload = null) {
  const wrap = document.createElement("div");
  wrap.className = "msg";

  const whoDiv = document.createElement("div");
  whoDiv.className = "who";
  whoDiv.textContent = who;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = html;

  wrap.appendChild(whoDiv);
  wrap.appendChild(bubble);

  if (sources.length) {
    const src = document.createElement("div");
    src.className = "sources";
    src.innerHTML = "<div><b>Surse</b></div>";
    const ul = document.createElement("ul");
    sources.forEach((url) => {
      const li = document.createElement("li");
      const safeUrl = esc(url);
      li.innerHTML = `<a href="${safeUrl}" target="_blank" rel="noreferrer">${safeUrl}</a>`;
      ul.appendChild(li);
    });
    src.appendChild(ul);
    wrap.appendChild(src);
  }

  if (feedbackPayload) {
    const feedback = document.createElement("div");
    feedback.className = "feedback";

    const up = document.createElement("button");
    up.type = "button";
    up.textContent = "Util";
    up.addEventListener("click", () => {
      sendFeedback({ ...feedbackPayload, vote: "up" });
      up.disabled = true;
      down.disabled = true;
    });

    const down = document.createElement("button");
    down.type = "button";
    down.textContent = "Inutil";
    down.addEventListener("click", () => {
      sendFeedback({ ...feedbackPayload, vote: "down" });
      up.disabled = true;
      down.disabled = true;
    });

    feedback.appendChild(up);
    feedback.appendChild(down);
    wrap.appendChild(feedback);
  }

  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
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
  const { sessionId } = await chrome.storage.local.get(["sessionId"]);
  if (sessionId) {
    return sessionId;
  }
  const nextSessionId = crypto.randomUUID();
  await chrome.storage.local.set({ sessionId: nextSessionId });
  return nextSessionId;
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
}

async function loadFaculties() {
  const { facultyId } = await chrome.storage.local.get(["facultyId"]);
  const selectedFacultyId = facultyId || "uvt";

  try {
    const response = await fetch(`${BACKEND_URL}/faculties`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    populateFaculties(data.faculties || FALLBACK_FACULTIES, selectedFacultyId);
  } catch (error) {
    populateFaculties(FALLBACK_FACULTIES, selectedFacultyId);
    setMeta("Lista de facultăți este în modul local fallback.");
  }
}

facultySelect.addEventListener("change", async () => {
  await chrome.storage.local.set({ facultyId: facultySelect.value });
});

async function send(prefilledQuestion = null) {
  const question = (prefilledQuestion ?? input.value).trim();
  if (!question) {
    return;
  }

  const sessionId = await ensureSessionId();
  const { facultyId } = await chrome.storage.local.get(["facultyId"]);
  const selectedFacultyId = facultyId || facultySelect.value || "uvt";
  const currentUrl = await getCurrentTabUrl();

  addMsg("Tu", esc(question));
  input.value = "";

  const pendingMessage = addMsg("UVT Asist", "Se caută răspuns...", []);

  try {
    const response = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        faculty_id: selectedFacultyId,
        current_url: currentUrl,
        session_id: sessionId
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    pendingMessage.remove();

    if (data.session_id && data.session_id !== sessionId) {
      await chrome.storage.local.set({ sessionId: data.session_id });
    }

    const metaBits = [];
    if (data.intent) {
      metaBits.push(`Intent: ${formatIntent(data.intent)}`);
    }
    if (data.matched_faculty) {
      metaBits.push(`Facultate: ${data.matched_faculty}`);
    }
    setMeta(metaBits.join(" | "));

    addMsg(
      "UVT Asist",
      esc(data.answer || ""),
      data.sources || [],
      {
        question,
        faculty_id: selectedFacultyId,
        current_url: currentUrl,
        session_id: data.session_id || sessionId,
        intent: data.intent || "general"
      }
    );
  } catch (error) {
    pendingMessage.remove();
    setMeta("Backend indisponibil.");
    addMsg("UVT Asist", "Eroare: backend indisponibil. Pornește Flask pe 127.0.0.1:5000", []);
  }
}

btn.addEventListener("click", () => {
  send();
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    send();
  }
});

document.querySelectorAll(".quick-btn").forEach((quickButton) => {
  quickButton.addEventListener("click", () => {
    send(quickButton.dataset.q || "");
  });
});

loadFaculties();
