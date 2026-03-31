(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarContextChange = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const PENDING_KEYS = [
    "pending_context_change",
    "pending_context_reason",
    "pending_context_entity_id",
    "pending_context_contract_id",
    "pending_context_auth_token",
  ];

  const SUBMISSION_STATES = Object.freeze({
    IDLE: "idle",
    SUBMITTING_CURRENT: "submitting_current",
    QUEUED_MORE: "queued_more",
  });

  function localGet(keys) {
    return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
  }

  function localSet(values) {
    return new Promise((resolve) => chrome.storage.local.set(values, resolve));
  }

  function localRemove(keys) {
    return new Promise((resolve) => chrome.storage.local.remove(keys, resolve));
  }

  function sessionGet(keys) {
    if (typeof chrome === "undefined" || !chrome.storage?.session) {
      return Promise.resolve({});
    }
    return new Promise((resolve) => chrome.storage.session.get(keys, resolve));
  }

  function sessionSet(values) {
    if (typeof chrome === "undefined" || !chrome.storage?.session) {
      return Promise.resolve();
    }
    return new Promise((resolve) => chrome.storage.session.set(values, resolve));
  }

  async function detectContextChange({ entity_id, contract_id, auth_token }) {
    const stored = await localGet(["masar_entity_id", "masar_contract_id"]);
    let reason = null;
    if (stored.masar_entity_id && entity_id && stored.masar_entity_id !== entity_id) {
      reason = "entity_changed";
    } else if (stored.masar_contract_id && contract_id && stored.masar_contract_id !== contract_id) {
      reason = "contract_changed";
    }
    if (!reason) {
      return null;
    }
    await localSet({
      pending_context_change: true,
      pending_context_reason: reason,
      pending_context_entity_id: entity_id || null,
      pending_context_contract_id: contract_id || null,
      pending_context_auth_token: auth_token || null,
    });
    return { reason };
  }

  async function applyContextChange() {
    const pending = await localGet(PENDING_KEYS);
    const nextValues = {};
    if (pending.pending_context_entity_id) {
      nextValues.masar_entity_id = pending.pending_context_entity_id;
    }
    if (pending.pending_context_contract_id) {
      nextValues.masar_contract_id = pending.pending_context_contract_id;
    }
    if (pending.pending_context_auth_token) {
      nextValues.masar_auth_token = pending.pending_context_auth_token;
    }
    if (Object.keys(nextValues).length) {
      await localSet(nextValues);
    }
    await localRemove([
      ...PENDING_KEYS,
      "masar_group_id",
      "masar_group_name",
      "masar_group_number",
      "masar_groups_cache",
    ]);
  }

  async function hasContextChangePending() {
    const pending = await localGet(["pending_context_change"]);
    return Boolean(pending.pending_context_change);
  }

  async function clearPendingContextChange() {
    await localRemove(PENDING_KEYS);
  }

  async function getContextChangeReason() {
    const pending = await localGet(["pending_context_reason"]);
    return pending.pending_context_reason || null;
  }

  function createDebouncedContextChecker(callback, delayMs) {
    let timer = null;
    return function debounced(context) {
      if (timer) {
        clearTimeout(timer);
      }
      timer = setTimeout(() => {
        timer = null;
        callback(context);
      }, delayMs);
    };
  }

  async function getSubmissionState() {
    const values = await sessionGet(["submission_state"]);
    return values.submission_state || SUBMISSION_STATES.IDLE;
  }

  async function setSubmissionState(state) {
    await sessionSet({ submission_state: state });
  }

  async function shouldStopSubmission() {
    const [state, pending] = await Promise.all([getSubmissionState(), hasContextChangePending()]);
    return pending && state !== SUBMISSION_STATES.SUBMITTING_CURRENT;
  }

  return {
    SUBMISSION_STATES,
    applyContextChange,
    clearPendingContextChange,
    createDebouncedContextChecker,
    detectContextChange,
    getContextChangeReason,
    getSubmissionState,
    hasContextChangePending,
    setSubmissionState,
    shouldStopSubmission,
  };
});
