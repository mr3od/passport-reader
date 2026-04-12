(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarContextChange = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const ACTIVE_UI_CONTEXT_KEY = "active_ui_context";
  const SUBMIT_BATCH_CONTEXT_KEY = "submit_batch_context";

  const SUBMISSION_STATES = Object.freeze({
    IDLE: "idle",
    SUBMITTING_CURRENT: "submitting_current",
    QUEUED_MORE: "queued_more",
  });

  function localGet(keys) {
    if (typeof chrome === "undefined" || !chrome.storage?.local) {
      return Promise.resolve({});
    }
    return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
  }

  function localSet(values) {
    if (typeof chrome === "undefined" || !chrome.storage?.local) {
      return Promise.resolve();
    }
    return new Promise((resolve) => chrome.storage.local.set(values, resolve));
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

  function sessionRemove(keys) {
    if (typeof chrome === "undefined" || !chrome.storage?.session) {
      return Promise.resolve();
    }
    return new Promise((resolve) => chrome.storage.session.remove(keys, resolve));
  }

  function getDefaultActiveUiContext() {
    return {
      entity_id: null,
      entity_type_id: null,
      auth_token: null,
      user_name: null,
      contract_id: null,
      contract_name: null,
      contract_name_ar: null,
      contract_name_en: null,
      contract_state: "unknown",
      requires_contract_confirmation: false,
      drift_reason: null,
      available_contracts: [],
    };
  }

  function normalizeActiveUiContext(value) {
    return {
      ...getDefaultActiveUiContext(),
      ...(value && typeof value === "object" ? value : {}),
      available_contracts: Array.isArray(value?.available_contracts) ? value.available_contracts : [],
    };
  }

  function activeUiContextsEqual(currentValue, nextValue) {
    const current = normalizeActiveUiContext(currentValue);
    const next = normalizeActiveUiContext(nextValue);
    return JSON.stringify(current) === JSON.stringify(next);
  }

  function normalizeSubmitBatchContext(value) {
    if (!value || typeof value !== "object") {
      return null;
    }
    return {
      entity_id: value.entity_id || null,
      entity_type_id: value.entity_type_id || null,
      contract_id: value.contract_id || null,
      contract_name: value.contract_name || null,
      auth_token: value.auth_token || null,
      started_at: value.started_at || null,
    };
  }

  function filterSelectableContracts(contracts) {
    return (Array.isArray(contracts) ? contracts : []).filter(isContractSelectable);
  }

  function getContractLifecycleState(contractEndDate) {
    if (!contractEndDate) {
      return "unknown";
    }
    const now = new Date();
    const end = new Date(contractEndDate);
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const endDayStart = new Date(end.getFullYear(), end.getMonth(), end.getDate());
    if (todayStart > endDayStart) {
      return "expired";
    }
    if (todayStart.getTime() === endDayStart.getTime()) {
      return "expires-today";
    }
    return "active";
  }

  function getSelectableContractState(contract) {
    const statusId =
      contract && contract.contractStatus && typeof contract.contractStatus.id !== "undefined"
        ? Number(contract.contractStatus.id)
        : null;
    if (statusId !== null && statusId !== 0) {
      return "inactive";
    }
    return getContractLifecycleState(contract?.contractEndDate);
  }

  function isContractSelectable(contract) {
    if (!contract || typeof contract !== "object") {
      return false;
    }
    const state = getSelectableContractState(contract);
    return state === "active" || state === "expires-today" || state === "unknown";
  }

  function classifyObservedContextChange(currentContext, observedContext) {
    const current = normalizeActiveUiContext(currentContext);
    const observedEntityId = observedContext?.entity_id || null;
    if (current.entity_id && observedEntityId && current.entity_id !== observedEntityId) {
      return "entity_changed_observed";
    }
    return null;
  }

  function deriveContractDisplay(contract) {
    return {
      contract_id: contract?.contractId ? String(contract.contractId) : null,
      contract_name: contract?.companyNameAr || contract?.companyNameEn || null,
      contract_name_ar: contract?.companyNameAr || null,
      contract_name_en: contract?.companyNameEn || null,
      contract_state: getSelectableContractState(contract),
    };
  }

  function clearContractSelection(currentContext, { availableContracts = null } = {}) {
    const current = normalizeActiveUiContext(currentContext);
    return {
      ...current,
      contract_id: null,
      contract_name: null,
      contract_name_ar: null,
      contract_name_en: null,
      contract_state: "unknown",
      available_contracts: Array.isArray(availableContracts) ? availableContracts : current.available_contracts,
    };
  }

  function resolveContractContext(currentContext, contracts, preferredContractId = null) {
    const current = normalizeActiveUiContext(currentContext);
    const selectableContracts = filterSelectableContracts(contracts);
    const selectedContract = preferredContractId
      ? selectableContracts.find((contract) => String(contract.contractId) === String(preferredContractId))
      : null;

    if (selectedContract) {
      return {
        mode: "selected",
        selectedContract,
        selectableContracts,
        nextContext: {
          ...clearContractSelection(current, { availableContracts: selectableContracts }),
          ...deriveContractDisplay(selectedContract),
          requires_contract_confirmation: false,
          drift_reason: null,
        },
      };
    }

    if (selectableContracts.length === 1) {
      return {
        mode: "selected",
        selectedContract: selectableContracts[0],
        selectableContracts,
        nextContext: {
          ...clearContractSelection(current, { availableContracts: selectableContracts }),
          ...deriveContractDisplay(selectableContracts[0]),
          requires_contract_confirmation: false,
          drift_reason: null,
        },
      };
    }

    if (selectableContracts.length === 0) {
      return {
        mode: "no-selectable-contracts",
        selectedContract: null,
        selectableContracts,
        nextContext: {
          ...clearContractSelection(current, { availableContracts: [] }),
          requires_contract_confirmation: false,
          drift_reason: null,
        },
      };
    }

    return {
      mode: "needs-contract-choice",
      selectedContract: null,
      selectableContracts,
      nextContext: {
        ...clearContractSelection(current, { availableContracts: selectableContracts }),
        requires_contract_confirmation: true,
        drift_reason: null,
      },
    };
  }

  function buildObservedEntityChangeContext(currentContext, observedContext, contracts) {
    const current = normalizeActiveUiContext(currentContext);
    return {
      ...current,
      entity_id: observedContext?.entity_id || null,
      entity_type_id: observedContext?.entity_type_id || null,
      auth_token: observedContext?.auth_token || current.auth_token || null,
      user_name: observedContext?.user_name || current.user_name || null,
      contract_id: null,
      contract_name: null,
      contract_name_ar: null,
      contract_name_en: null,
      contract_state: "unknown",
      requires_contract_confirmation: true,
      drift_reason: "entity_changed_observed",
      available_contracts: filterSelectableContracts(contracts),
    };
  }

  function buildExplicitContractSelectionContext(currentContext, contract) {
    const current = normalizeActiveUiContext(currentContext);
    const contractDisplay = deriveContractDisplay(contract);
    return {
      ...current,
      ...contractDisplay,
      requires_contract_confirmation: false,
      drift_reason: null,
    };
  }

  function buildLegacyStoragePatch(context) {
    const active = normalizeActiveUiContext(context);
    return {
      masar_entity_id: active.entity_id || "",
      masar_entity_type_id: active.entity_type_id || "",
      masar_auth_token: active.auth_token || "",
      masar_user_name: active.user_name || "",
      masar_contract_id: active.contract_id || "",
      masar_contract_name_ar: active.contract_name_ar || "",
      masar_contract_name_en: active.contract_name_en || "",
      masar_contract_state: active.contract_state || "unknown",
    };
  }

  async function getActiveUiContext() {
    const values = await localGet([ACTIVE_UI_CONTEXT_KEY]);
    return normalizeActiveUiContext(values[ACTIVE_UI_CONTEXT_KEY]);
  }

  async function setActiveUiContext(nextContext) {
    const normalized = normalizeActiveUiContext(nextContext);
    const currentValues = await localGet([ACTIVE_UI_CONTEXT_KEY]);
    const current = normalizeActiveUiContext(currentValues[ACTIVE_UI_CONTEXT_KEY]);
    if (activeUiContextsEqual(current, normalized)) {
      return current;
    }
    await localSet({
      [ACTIVE_UI_CONTEXT_KEY]: normalized,
      ...buildLegacyStoragePatch(normalized),
    });
    return normalized;
  }

  async function getSubmitBatchContext() {
    const values = await sessionGet([SUBMIT_BATCH_CONTEXT_KEY]);
    return normalizeSubmitBatchContext(values[SUBMIT_BATCH_CONTEXT_KEY]);
  }

  async function setSubmitBatchContext(context) {
    const normalized = normalizeSubmitBatchContext(context);
    await sessionSet({ [SUBMIT_BATCH_CONTEXT_KEY]: normalized });
    return normalized;
  }

  async function clearSubmitBatchContext() {
    await sessionRemove([SUBMIT_BATCH_CONTEXT_KEY]);
  }

  async function hasContextChangePending() {
    const active = await getActiveUiContext();
    return Boolean(
      active.drift_reason
      || active.requires_contract_confirmation
    );
  }

  async function getContextChangeReason() {
    const active = await getActiveUiContext();
    return active.drift_reason || null;
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

  async function clearPendingContextChange() {
    const current = await getActiveUiContext();
    await setActiveUiContext({
      ...current,
      drift_reason: null,
      requires_contract_confirmation: false,
    });
  }

  return {
    ACTIVE_UI_CONTEXT_KEY,
    SUBMIT_BATCH_CONTEXT_KEY,
    SUBMISSION_STATES,
    buildExplicitContractSelectionContext,
    buildLegacyStoragePatch,
    buildObservedEntityChangeContext,
    activeUiContextsEqual,
    classifyObservedContextChange,
    clearPendingContextChange,
    clearSubmitBatchContext,
    createDebouncedContextChecker,
    filterSelectableContracts,
    getActiveUiContext,
    getContextChangeReason,
    getDefaultActiveUiContext,
    resolveContractContext,
    getSelectableContractState,
    getSubmitBatchContext,
    getSubmissionState,
    hasContextChangePending,
    isContractSelectable,
    normalizeActiveUiContext,
    normalizeSubmitBatchContext,
    setActiveUiContext,
    setSubmitBatchContext,
    setSubmissionState,
  };
});
