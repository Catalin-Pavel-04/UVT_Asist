"use strict";

(function exposeApi(global) {
  const DEFAULT_BACKEND_URL = "http://127.0.0.1:5000";
  const REQUEST_TIMEOUT_MS = {
    health: 6000,
    faculties: 6000,
    feedback: 8000,
    chat: 150000
  };

  async function getBackendUrl() {
    if (global.UVTStorage?.loadBackendUrl) {
      return global.UVTStorage.loadBackendUrl();
    }
    return DEFAULT_BACKEND_URL;
  }

  async function fetchJson(path, options = {}, timeoutMs = REQUEST_TIMEOUT_MS.health) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const backendUrl = await getBackendUrl();
      const response = await fetch(`${backendUrl}${path}`, {
        ...options,
        signal: controller.signal
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const message = data?.answer || data?.message || `HTTP ${response.status}`;
        const httpError = new Error(message);
        httpError.status = response.status;
        httpError.payload = data;
        throw httpError;
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError") {
        throw new Error("Cererea a depășit timpul de așteptare.");
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function checkBackend() {
    return fetchJson("/health", {}, REQUEST_TIMEOUT_MS.health);
  }

  function getFaculties() {
    return fetchJson("/faculties", {}, REQUEST_TIMEOUT_MS.faculties);
  }

  function getIndexingStatus() {
    return fetchJson("/indexing/status", {}, REQUEST_TIMEOUT_MS.health);
  }

  function sendChatMessage({ question, facultyId, history }) {
    return fetchJson(
      "/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, faculty_id: facultyId, history })
      },
      REQUEST_TIMEOUT_MS.chat
    );
  }

  function postFeedback(payload) {
    return fetchJson(
      "/feedback",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      },
      REQUEST_TIMEOUT_MS.feedback
    );
  }

  global.UVTApi = {
    DEFAULT_BACKEND_URL,
    REQUEST_TIMEOUT_MS,
    getBackendUrl,
    fetchJson,
    checkBackend,
    getFaculties,
    getIndexingStatus,
    sendChatMessage,
    postFeedback
  };
})(globalThis);
