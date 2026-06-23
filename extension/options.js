"use strict";

const refs = {
  form: document.getElementById("optionsForm"),
  backendUrl: document.getElementById("backendUrl"),
  resetBackendUrl: document.getElementById("resetBackendUrl"),
  statusMessage: document.getElementById("statusMessage")
};

function setStatus(message, kind = "") {
  refs.statusMessage.textContent = message;
  refs.statusMessage.className = `status-message ${kind}`.trim();
}

async function loadOptions() {
  refs.backendUrl.value = await UVTStorage.loadBackendUrl();
}

async function saveOptions(event) {
  event.preventDefault();

  try {
    const savedUrl = await UVTStorage.saveBackendUrl(refs.backendUrl.value);
    refs.backendUrl.value = savedUrl;
    setStatus("Backend URL salvat.", "success");
  } catch (error) {
    setStatus(error.message || "Backend URL invalid.", "error");
  }
}

async function resetBackendUrl() {
  const savedUrl = await UVTStorage.saveBackendUrl(UVTStorage.DEFAULT_BACKEND_URL);
  refs.backendUrl.value = savedUrl;
  setStatus("Backend URL resetat la valoarea implicită.", "success");
}

refs.form.addEventListener("submit", saveOptions);
refs.resetBackendUrl.addEventListener("click", resetBackendUrl);
refs.backendUrl.addEventListener("input", () => setStatus(""));

loadOptions();
