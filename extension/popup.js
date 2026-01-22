const log = document.getElementById("log");
const input = document.getElementById("q");
const btn = document.getElementById("send");
const facultySelect = document.getElementById("faculty");

function esc(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function addMsg(who, html, sources=[]) {
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

  if (sources && sources.length) {
    const s = document.createElement("div");
    s.className = "sources";
    s.innerHTML = "<div><b>Surse</b></div>";
    const ul = document.createElement("ul");
    for (const url of sources) {
      const li = document.createElement("li");
      const safe = esc(url);
      li.innerHTML = `<a href="${safe}" target="_blank" rel="noreferrer">${safe}</a>`;
      ul.appendChild(li);
    }
    s.appendChild(ul);
    wrap.appendChild(s);
  }

  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

async function loadFaculties() {
  const res = await chrome.storage.local.get(["facultyId"]);
  const saved = res.facultyId || "uvt";

  try {
    const r = await fetch("http://127.0.0.1:5000/faculties");
    const data = await r.json();

    facultySelect.innerHTML = "";
    for (const f of data.faculties) {
      const opt = document.createElement("option");
      opt.value = f.id;
      opt.textContent = f.name;
      facultySelect.appendChild(opt);
    }
    facultySelect.value = saved;
  } catch (e) {
    facultySelect.innerHTML = `
      <option value="uvt">UVT (general)</option>
      <option value="fmi">Facultatea de Matematică și Informatică</option>
      <option value="feaa">FEAA</option>
    `;
    facultySelect.value = saved;
  }
}

facultySelect.addEventListener("change", async () => {
  await chrome.storage.local.set({ facultyId: facultySelect.value });
});

async function send() {
  const q = input.value.trim();
  if (!q) return;

  const { facultyId } = await chrome.storage.local.get(["facultyId"]);
  const fid = facultyId || facultySelect.value || "uvt";

  addMsg("Tu", esc(q));
  input.value = "";

  addMsg("UVT Asist", "Se caută răspuns...", []);

  try {
    const resp = await fetch("http://127.0.0.1:5000/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, faculty_id: fid })
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const data = await resp.json();

    // Remove placeholder
    log.removeChild(log.lastChild);

    const answerHtml = esc(data.answer || "");
    addMsg("UVT Asist", answerHtml, data.sources || []);
  } catch (e) {
    log.removeChild(log.lastChild);
    addMsg("UVT Asist", "Eroare: backend indisponibil. Pornește Flask pe 127.0.0.1:5000", []);
  }
}

btn.addEventListener("click", send);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") send();
});

loadFaculties();
