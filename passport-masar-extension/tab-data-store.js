(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarTabDataStore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const TAB_NAMES = ["pending", "submitted", "failed"];

  function createEmptyTab() {
    return {
      items: [],
      hasMore: false,
      total: 0,
      offset: 0,
      error: null,
    };
  }

  function normalizePage(page = {}, fallbackItems = []) {
    return {
      items: Array.isArray(page.items) ? page.items.slice() : fallbackItems.slice(),
      hasMore: Boolean(page.hasMore),
      total: Number.isFinite(page.total) ? page.total : 0,
      offset: Number.isFinite(page.offset) ? page.offset : 0,
      error: null,
    };
  }

  function ensureTab(store, tab) {
    if (!TAB_NAMES.includes(tab)) {
      throw new Error(`Unknown tab: ${tab}`);
    }
    return store[tab] || createEmptyTab();
  }

  function create() {
    return {
      pending: createEmptyTab(),
      submitted: createEmptyTab(),
      failed: createEmptyTab(),
    };
  }

  function setPage(store, tab, page) {
    const current = ensureTab(store, tab);
    return {
      ...store,
      [tab]: normalizePage(page, current.items),
    };
  }

  function appendPage(store, tab, page) {
    const current = ensureTab(store, tab);
    const nextPage = normalizePage(page, current.items);
    return {
      ...store,
      [tab]: {
        ...nextPage,
        items: current.items.concat(nextPage.items),
      },
    };
  }

  function setError(store, tab, error) {
    const current = ensureTab(store, tab);
    return {
      ...store,
      [tab]: {
        ...current,
        error,
      },
    };
  }

  function getTab(store, tab) {
    return ensureTab(store, tab);
  }

  return {
    appendPage,
    create,
    getTab,
    setError,
    setPage,
  };
});
