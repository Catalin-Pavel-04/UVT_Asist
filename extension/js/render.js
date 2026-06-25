"use strict";

(function exposeRender(global) {
  function createRefs() {
    return {
      log: document.getElementById("log"),
      input: document.getElementById("q"),
      send: document.getElementById("send"),
      faculty: document.getElementById("faculty"),
      facultyBadge: document.getElementById("facultyBadge"),
      emptyState: document.getElementById("emptyState"),
      emptyText: document.getElementById("emptyText"),
      statusDot: document.getElementById("statusDot"),
      backendModeBadge: document.getElementById("backendModeBadge"),
      themeToggle: document.getElementById("themeToggle"),
      clearConversation: document.getElementById("clearConversation"),
      copyAnswer: document.getElementById("copyAnswer"),
      recentPanel: document.getElementById("recentPanel"),
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
  }

  function setBackendOnline(refs, online) {
    refs.statusDot.classList.toggle("online", online);
    if (refs.backendModeBadge) {
      refs.backendModeBadge.hidden = !online;
    }
  }

  function setStatus(refs, kind, title, text) {
    const showPanel = kind === "loading" || kind === "warning" || kind === "error";
    refs.statusPanel.className = `status-panel status-${kind}`;
    refs.statusPanel.hidden = !showPanel;
    refs.statusTitle.textContent = title;
    refs.statusText.textContent = text;
  }

  function updateControlState(refs, snapshot) {
    const busy = Boolean(snapshot.sending || snapshot.indexing);
    const backendUnavailable = snapshot.backendAvailable === false;
    const hasRenderedMessages = refs.log.querySelectorAll(".msg").length > 0;
    const hasHistory = (Array.isArray(snapshot.history) && snapshot.history.length > 0) || hasRenderedMessages;
    refs.send.disabled = busy || backendUnavailable;
    refs.send.title = backendUnavailable
      ? "Pornește backendul Flask local pentru a trimite întrebări."
      : "";
    refs.input.disabled = busy;
    refs.faculty.disabled = busy;
    refs.chips.forEach((chip) => {
      chip.disabled = busy || backendUnavailable;
    });
    refs.clearConversation.disabled = busy || !hasHistory;
    refs.copyAnswer.disabled = busy || !snapshot.hasAssistant;
  }

  function clampProgress(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    return Math.max(0, Math.min(100, Math.round(numeric)));
  }

  function renderIndexingProgress(refs, indexing) {
    const running = Boolean(indexing?.running);

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

  function updateFacultyBadge(refs) {
    const label = refs.faculty.options[refs.faculty.selectedIndex]?.text || "UVT";
    refs.facultyBadge.textContent = label.length > 26 ? `${label.slice(0, 26)}...` : label;
  }

  function clearLog(refs) {
    refs.log.innerHTML = "";
    refs.log.appendChild(refs.emptyState);
  }

  function hasConversation(refs) {
    const hasMessages = refs.log.querySelectorAll(".msg").length > 0;
    return hasMessages;
  }

  function syncRecentPanel(refs) {
    if (!refs.recentPanel) {
      return;
    }
    refs.recentPanel.open = !hasConversation(refs);
  }

  function toggleEmptyState(refs) {
    const hasMessages = hasConversation(refs);
    refs.emptyState.hidden = hasMessages;
    syncRecentPanel(refs);
  }

  function scrollToBottom(refs) {
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

  function addUserMessage(refs, text) {
    refs.log.appendChild(createMessage("user", "Tu", text));
    toggleEmptyState(refs);
    scrollToBottom(refs);
  }

  function createLoadingDots() {
    const loading = document.createElement("div");
    loading.className = "loading";
    for (let index = 0; index < 3; index += 1) {
      loading.appendChild(document.createElement("span"));
    }
    return loading;
  }

  function addLoadingMessage(refs) {
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
    toggleEmptyState(refs);
    scrollToBottom(refs);
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
      const verified = false;
      const card = document.createElement("article");
      card.className = `source-card ${verified ? "verified" : "local-index"}`;

      const head = document.createElement("div");
      head.className = "source-head";

      const label = document.createElement("div");
      label.className = "source-label";
      label.textContent = source.title || "Sursă oficială";

      const badge = document.createElement("span");
      badge.className = `source-status-badge ${verified ? "verified" : "local-index"}`;
      badge.textContent = "Index local";
      badge.title = "Sursa provine din indexul local.";

      const link = document.createElement("a");
      link.className = "source-link";
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = formatSourceUrl(source.url);
      link.title = source.url;

      head.append(label, badge);
      card.append(head, link);
      block.appendChild(card);
    });

    return block;
  }

  function createFeedbackActions(payload, onFeedback) {
    if (!payload || typeof onFeedback !== "function") {
      return null;
    }

    const block = document.createElement("div");
    block.className = "feedback-actions";

    const useful = document.createElement("button");
    useful.type = "button";
    useful.className = "feedback-btn positive";
    useful.textContent = "Util";

    const inaccurate = document.createElement("button");
    inaccurate.type = "button";
    inaccurate.className = "feedback-btn negative";
    inaccurate.textContent = "Inexact";

    const stateText = document.createElement("span");
    stateText.className = "feedback-state";

    async function sendFeedback(value) {
      useful.disabled = true;
      inaccurate.disabled = true;
      stateText.textContent = "Se salvează...";
      try {
        await onFeedback({ ...payload, feedback: value, created_at: new Date().toISOString() });
        stateText.textContent = "Salvat";
      } catch {
        stateText.textContent = "Netrimis";
        useful.disabled = false;
        inaccurate.disabled = false;
      }
    }

    useful.addEventListener("click", () => sendFeedback("positive"));
    inaccurate.addEventListener("click", () => sendFeedback("negative"));
    block.append(useful, inaccurate, stateText);
    return block;
  }

  function addBotMessage(refs, text, sources = [], feedbackPayload = null, onFeedback = null, responseMeta = null) {
    refs.log.appendChild(createMessage("bot", "UVT Asist", text));

    const metaBlock = createResponseMetaBlock(responseMeta || feedbackPayload || {}, sources);
    if (metaBlock) {
      refs.log.appendChild(metaBlock);
    }

    const sourceBlock = createSourcesBlock(sources);
    if (sourceBlock) {
      refs.log.appendChild(sourceBlock);
    }

    const feedback = createFeedbackActions(feedbackPayload, onFeedback);
    if (feedback) {
      refs.log.appendChild(feedback);
    }

    toggleEmptyState(refs);
    scrollToBottom(refs);
  }

  function renderConversation(refs, history, callbacks = {}) {
    clearLog(refs);
    history.forEach((entry) => {
      if (entry.role === "user") {
        addUserMessage(refs, entry.text);
      } else {
        addBotMessage(refs, entry.text, entry.sources, null, callbacks.onFeedback, entry.meta);
      }
    });
    toggleEmptyState(refs);
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

  function createMetaChip(text, tone = "muted", title = "") {
    const chip = document.createElement("span");
    chip.className = `response-meta-chip ${tone}`;
    chip.textContent = text;
    if (title) {
      chip.title = title;
    }
    return chip;
  }

  function createResponseMetaBlock(meta = {}, sources = []) {
    const chips = [];
    const confidence = meta.confidence;
    const score = Number(meta.confidence_score);
    const evidence = meta.evidence || {};
    const sourceCountValue = Number(evidence.source_count);
    const sourceCount = Number.isFinite(sourceCountValue) && sourceCountValue > 0
      ? sourceCountValue
      : sources.length;
    if (confidence) {
      const label = Number.isFinite(score) && score > 0
        ? `Încredere ${confidence} (${Math.round(score)})`
        : `Încredere ${confidence}`;
      chips.push(createMetaChip(label, confidenceTone(confidence), meta.confidence_reason || ""));
    }

    if (meta.retrieval_backend || sourceCount > 0) {
      const backend = String(meta.retrieval_backend || "");
      const backendLabel = backend && !["qdrant", "local_json_lexical", "local_json_fallback"].includes(backend)
        ? backend
        : "Index local";
      chips.push(createMetaChip(backendLabel, "muted", "Răspuns construit din sursele indexate local."));
    }

    if (sourceCount > 0) {
      chips.push(createMetaChip(`${sourceCount} ${sourceCount === 1 ? "sursă" : "surse"}`, "muted"));
    }

    if (!chips.length) {
      return null;
    }

    const block = document.createElement("div");
    block.className = "response-meta";
    block.append(...chips);
    return block;
  }

  function renderRecentQuestions(refs, questions = [], onClick) {
    refs.recentQuestions.innerHTML = "";
    questions.forEach((question) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "recent-item";
      item.textContent = question;
      item.title = question;
      item.addEventListener("click", () => onClick(question));
      refs.recentQuestions.appendChild(item);
    });
    refs.recentPanel?.classList.toggle("has-items", questions.length > 0);
    syncRecentPanel(refs);
  }

  function populateFaculties(refs, faculties, selectedFacultyId) {
    refs.faculty.innerHTML = "";
    faculties.forEach((faculty) => {
      const option = document.createElement("option");
      option.value = faculty.id;
      option.textContent = faculty.name;
      refs.faculty.appendChild(option);
    });

    const ids = new Set(faculties.map((faculty) => faculty.id));
    refs.faculty.value = ids.has(selectedFacultyId) ? selectedFacultyId : "uvt";
    updateFacultyBadge(refs);
    return refs.faculty.value;
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
      messages.push("Ollama local nu răspunde. Pornește `ollama serve`.");
    } else {
      if (checks.generation_model === false || ollama.generation_model_available === false) {
        messages.push(`Modelul local de generare lipsește. Rulează \`ollama pull ${generationModel}\`.`);
      }
      if (checks.embedding_model === false || ollama.embedding_model_available === false) {
        messages.push(`Modelul local de embedding lipsește. Rulează \`ollama pull ${embeddingModel}\`.`);
      }
    }

    if (checks.json_index === false || index.exists === false || chunkCount === 0) {
      messages.push("Indexul local lipsește. Rulează `python backend/build_index.py`.");
    }

    if (checks.qdrant_index === false || vectorIndex.available === false || vectorCount === 0) {
      if (vectorIndex.available === false || vectorIndex.exists === false) {
        messages.push("Qdrant local este indisponibil. Rulează `docker compose up -d qdrant`.");
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

  function applyTheme(refs, theme) {
    const dark = theme === "dark";
    document.body.classList.toggle("dark", dark);
    refs.themeToggle.textContent = dark ? "Light" : "Dark";
    refs.themeToggle.title = dark ? "Comută pe tema deschisă" : "Comută pe tema închisă";
  }

  global.UVTRender = {
    createRefs,
    setBackendOnline,
    setStatus,
    updateControlState,
    renderIndexingProgress,
    updateFacultyBadge,
    clearLog,
    toggleEmptyState,
    scrollToBottom,
    hasConversation,
    createMessage,
    addUserMessage,
    addBotMessage,
    addLoadingMessage,
    removeLoadingMessage,
    renderConversation,
    renderRecentQuestions,
    populateFaculties,
    buildHealthMessages,
    applyTheme
  };
})(globalThis);
