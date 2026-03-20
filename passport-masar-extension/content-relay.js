// Runs in ISOLATED world — has access to chrome.runtime.
// Receives postMessage from content-main.js and forwards to the service worker.
const RELAY_TYPES = new Set(["GROUP_LIST_CAPTURED", "CONTRACT_LIST_CAPTURED"]);
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (!event.data || !RELAY_TYPES.has(event.data.__masarExt)) return;
  chrome.runtime.sendMessage({ type: event.data.__masarExt, data: event.data.data });
});
