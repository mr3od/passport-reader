(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarBadge = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function computeBadgeState({ sessionExpired, contextChangePending, failedCount }) {
    if (sessionExpired) {
      return { text: "!", color: "#D32F2F", priority: 1 };
    }
    if (contextChangePending) {
      return { text: "!", color: "#F57C00", priority: 2 };
    }
    if (failedCount > 0) {
      return { text: String(failedCount), color: "#D32F2F", priority: 3 };
    }
    return { text: "", color: "", priority: 4 };
  }

  async function applyBadge({ text, color }) {
    if (typeof chrome === "undefined" || !chrome.action) {
      return;
    }
    await chrome.action.setBadgeText({ text });
    if (text && color) {
      await chrome.action.setBadgeBackgroundColor({ color });
    }
  }

  return {
    applyBadge,
    computeBadgeState,
  };
});
