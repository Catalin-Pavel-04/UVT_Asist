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
      sources: entry.sources ? [...entry.sources] : []
    }));
  }

  function clearHistory() {
    state.history = [];
  }

  function appendHistory(role, text, sources = []) {
    const entry = normalizeHistoryEntry({ role, text, sources });
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
