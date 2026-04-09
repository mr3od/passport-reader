(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarTabFetchCoordinator = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const TAB_NAMES = ["pending", "submitted", "failed"];
  const PAGE_SIZE = 50;

  function createTabState() {
    return {
      status: "idle",
      dirty: true,
      requestId: 0,
    };
  }

  function ensureTab(coordinator, tab) {
    if (!TAB_NAMES.includes(tab)) {
      throw new Error(`Unknown tab: ${tab}`);
    }
    return coordinator[tab] || createTabState();
  }

  function updateTab(coordinator, tab, nextTab) {
    return {
      ...coordinator,
      [tab]: nextTab,
    };
  }

  function create() {
    return {
      pending: createTabState(),
      submitted: createTabState(),
      failed: createTabState(),
    };
  }

  function beginFetch(coordinator, tab) {
    const current = ensureTab(coordinator, tab);
    const requestId = current.requestId + 1;
    return {
      nextCoordinator: updateTab(coordinator, tab, {
        ...current,
        status: "loading",
        requestId,
      }),
      requestId,
    };
  }

  function commitSuccess(coordinator, tab, requestId) {
    const current = ensureTab(coordinator, tab);
    if (current.requestId !== requestId) {
      return { coordinator, accepted: false };
    }
    return {
      coordinator: updateTab(coordinator, tab, {
        ...current,
        status: "ready",
        dirty: false,
      }),
      accepted: true,
    };
  }

  function commitError(coordinator, tab, requestId) {
    const current = ensureTab(coordinator, tab);
    if (current.requestId !== requestId) {
      return { coordinator, accepted: false };
    }
    return {
      coordinator: updateTab(coordinator, tab, {
        ...current,
        status: "error",
      }),
      accepted: true,
    };
  }

  function markDirty(coordinator, tab) {
    const current = ensureTab(coordinator, tab);
    return updateTab(coordinator, tab, {
      ...current,
      dirty: true,
    });
  }

  function markAllDirty(coordinator) {
    return TAB_NAMES.reduce((nextCoordinator, tab) => markDirty(nextCoordinator, tab), coordinator);
  }

  function isLoading(coordinator, tab) {
    return ensureTab(coordinator, tab).status === "loading";
  }

  function isDirty(coordinator, tab) {
    return ensureTab(coordinator, tab).dirty;
  }

  function getPageSize() {
    return PAGE_SIZE;
  }

  return {
    beginFetch,
    commitError,
    commitSuccess,
    create,
    getPageSize,
    isDirty,
    isLoading,
    markAllDirty,
    markDirty,
  };
});
