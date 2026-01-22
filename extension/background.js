chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["facultyId"], (res) => {
    if (!res.facultyId) chrome.storage.local.set({ facultyId: "uvt" });
  });
});
