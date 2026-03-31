(function (root, factory) {
  const api = factory(root.MasarStrings || require("./strings.js"));
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarNotifications = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (strings) {
  const NOTIFICATION_TYPES = Object.freeze({
    CONTEXT_CHANGE: "context-change",
    SESSION_EXPIRED: "session-expired",
    BATCH_COMPLETE: "batch-complete",
  });

  const dedup = new Map();

  function getNotificationTitle(type) {
    if (type === NOTIFICATION_TYPES.CONTEXT_CHANGE) {
      return strings.NOTIF_CONTEXT_CHANGE;
    }
    if (type === NOTIFICATION_TYPES.SESSION_EXPIRED) {
      return strings.NOTIF_SESSION_EXPIRED;
    }
    return strings.NOTIF_BATCH_COMPLETE;
  }

  async function notify(type, message, title) {
    const now = Date.now();
    const last = dedup.get(type) || 0;
    if (now - last < 30000) {
      return;
    }
    dedup.set(type, now);
    if (typeof chrome === "undefined" || !chrome.notifications) {
      return;
    }
    await chrome.notifications.create(`masar-${type}-${now}`, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: title || getNotificationTitle(type),
      message,
    });
  }

  return {
    NOTIFICATION_TYPES,
    getNotificationTitle,
    notify,
  };
});
