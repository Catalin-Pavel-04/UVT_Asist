"use strict";

(function exposeState(global) {
  const MAX_HISTORY_MESSAGES = 10;

  const state = {
    sending: false,
    indexing: false,
    history: []
  };

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

  function normalizeResponseMeta(meta = {}) {
    if (!meta || typeof meta !== "object") {
      return {};
    }

    return {
      confidence: meta.confidence || "",
      confidence_score: Number.isFinite(Number(meta.confidence_score)) ? Number(meta.confidence_score) : 0,
      confidence_reason: meta.confidence_reason || "",
      live_verified: Boolean(meta.live_verified),
      retrieval_backend: meta.retrieval_backend || "",
      generation_mode: meta.generation_mode || "",
      evidence: meta.evidence && typeof meta.evidence === "object"
        ? {
            source_count: Number.isFinite(Number(meta.evidence.source_count)) ? Number(meta.evidence.source_count) : 0,
            verified_source_count: Number.isFinite(Number(meta.evidence.verified_source_count))
              ? Number(meta.evidence.verified_source_count)
              : 0
          }
        : {}
    };
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
      sources: entry.role === "assistant" ? normalizeSources(entry.sources || []) : [],
      meta: entry.role === "assistant" ? normalizeResponseMeta(entry.meta || entry) : {}
    };
  }

  function setSending(value) {
    state.sending = Boolean(value);
  }

  function setIndexing(value) {
    state.indexing = Boolean(value);
  }

  function setHistory(items) {
    state.history = (Array.isArray(items) ? items : [])
      .map(normalizeHistoryEntry)
      .filter(Boolean)
      .slice(-MAX_HISTORY_MESSAGES);
  }

  function getHistory() {
    return state.history.map((entry) => ({
      role: entry.role,
      text: entry.text,
      sources: entry.sources ? [...entry.sources] : [],
      meta: entry.meta ? { ...entry.meta, evidence: { ...(entry.meta.evidence || {}) } } : {}
    }));
  }

  function clearHistory() {
    state.history = [];
  }

  function appendHistory(role, text, sources = [], meta = {}) {
    const entry = normalizeHistoryEntry({ role, text, sources, meta });
    if (!entry) {
      return;
    }
    state.history = [...state.history, entry].slice(-MAX_HISTORY_MESSAGES);
  }

  function buildHistoryPayload() {
    return state.history.map((entry) => ({ role: entry.role, content: entry.text }));
  }

  function getLastAssistantMessage() {
    for (let index = state.history.length - 1; index >= 0; index -= 1) {
      if (state.history[index].role === "assistant") {
        return state.history[index];
      }
    }
    return null;
  }

  function isSending() {
    return state.sending;
  }

  function isIndexing() {
    return state.indexing;
  }

  function getSnapshot() {
    return {
      sending: state.sending,
      indexing: state.indexing,
      history: getHistory(),
      hasAssistant: Boolean(getLastAssistantMessage())
    };
  }

  global.UVTState = {
    MAX_HISTORY_MESSAGES,
    normalizeSources,
    normalizeResponseMeta,
    normalizeHistoryEntry,
    setSending,
    setIndexing,
    setHistory,
    getHistory,
    clearHistory,
    appendHistory,
    buildHistoryPayload,
    getLastAssistantMessage,
    isSending,
    isIndexing,
    getSnapshot
  };
})(globalThis);
