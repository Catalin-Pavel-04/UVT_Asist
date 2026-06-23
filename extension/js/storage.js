"use strict";

(function exposeStorage(global) {
  const RECENT_QUESTIONS_KEY = "recentQuestions";
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

  global.UVTStorage = {
    RECENT_QUESTIONS_KEY,
    storageGet,
    storageSet,
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
