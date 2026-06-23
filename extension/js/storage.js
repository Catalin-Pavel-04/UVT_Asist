"use strict";

(function exposeStorage(global) {
  const RECENT_QUESTIONS_KEY = "recentQuestions";
  const BACKEND_URL_KEY = "backendUrl";
  const DEFAULT_BACKEND_URL = "http://127.0.0.1:5000";
  const ALLOWED_BACKEND_ORIGINS = new Set([
    "http://127.0.0.1:5000",
    "http://localhost:5000"
  ]);
  const MAX_RECENT_QUESTIONS = 5;

  function storageGet(keys) {
    return chrome.storage.local.get(keys);
  }

  function storageSet(value) {
    return chrome.storage.local.set(value);
  }

  function getHistoryStorageKey(facultyId) {
    return `chatHistory:${facultyId || "uvt"}`;
  }

  async function loadConversationHistory(facultyId) {
    const key = getHistoryStorageKey(facultyId);
    const stored = await storageGet([key]);
    return Array.isArray(stored[key]) ? stored[key] : [];
  }

  function saveConversationHistory(facultyId, history) {
    return storageSet({ [getHistoryStorageKey(facultyId)]: history });
  }

  async function loadRecentQuestions() {
    const stored = await storageGet([RECENT_QUESTIONS_KEY]);
    return Array.isArray(stored[RECENT_QUESTIONS_KEY]) ? stored[RECENT_QUESTIONS_KEY] : [];
  }

  async function saveRecentQuestion(question) {
    const value = question.trim();
    if (!value) {
      return loadRecentQuestions();
    }

    const recent = await loadRecentQuestions();
    const next = [value, ...recent.filter((item) => item !== value)].slice(0, MAX_RECENT_QUESTIONS);
    await storageSet({ [RECENT_QUESTIONS_KEY]: next });
    return next;
  }

  async function loadFacultyId() {
    const stored = await storageGet(["facultyId"]);
    return stored.facultyId || "uvt";
  }

  function saveFacultyId(facultyId) {
    return storageSet({ facultyId });
  }

  async function loadTheme() {
    const stored = await storageGet(["theme"]);
    return stored.theme || "light";
  }

  function saveTheme(theme) {
    return storageSet({ theme });
  }

  function normalizeBackendUrl(value) {
    const raw = String(value || "").trim().replace(/\/+$/, "");
    if (!raw) {
      throw new Error("Completeaza URL-ul backendului local.");
    }

    let parsed;
    try {
      parsed = new URL(raw);
    } catch {
      throw new Error("URL-ul backendului nu este valid.");
    }

    if (!raw.startsWith("http://127.0.0.1") && !raw.startsWith("http://localhost")) {
      throw new Error("Sunt permise doar URL-uri locale: http://127.0.0.1:5000 sau http://localhost:5000.");
    }

    if (!ALLOWED_BACKEND_ORIGINS.has(parsed.origin)) {
      throw new Error("URL-ul trebuie sa fie http://127.0.0.1:5000 sau http://localhost:5000.");
    }

    if (parsed.pathname !== "/" && parsed.pathname !== "") {
      throw new Error("Introdu doar origin-ul backendului, fara cale suplimentara.");
    }

    return parsed.origin;
  }

  function isAllowedBackendUrl(value) {
    try {
      normalizeBackendUrl(value);
      return true;
    } catch {
      return false;
    }
  }

  async function loadBackendUrl() {
    const stored = await storageGet([BACKEND_URL_KEY]);
    try {
      return normalizeBackendUrl(stored[BACKEND_URL_KEY] || DEFAULT_BACKEND_URL);
    } catch {
      return DEFAULT_BACKEND_URL;
    }
  }

  async function saveBackendUrl(value) {
    const backendUrl = normalizeBackendUrl(value);
    await storageSet({ [BACKEND_URL_KEY]: backendUrl });
    return backendUrl;
  }

  global.UVTStorage = {
    RECENT_QUESTIONS_KEY,
    BACKEND_URL_KEY,
    DEFAULT_BACKEND_URL,
    storageGet,
    storageSet,
    normalizeBackendUrl,
    isAllowedBackendUrl,
    loadBackendUrl,
    saveBackendUrl,
    getHistoryStorageKey,
    loadConversationHistory,
    saveConversationHistory,
    loadRecentQuestions,
    saveRecentQuestion,
    loadFacultyId,
    saveFacultyId,
    loadTheme,
    saveTheme
  };
})(globalThis);
