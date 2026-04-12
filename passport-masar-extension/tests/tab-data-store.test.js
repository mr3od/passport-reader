const test = require("node:test");
const assert = require("node:assert/strict");

const TabDataStore = require("../tab-data-store.js");

test("TabDataStore.create builds the server-backed tabs without inProgress", () => {
  const store = TabDataStore.create();

  assert.deepEqual(Object.keys(store).sort(), ["failed", "pending", "submitted"]);
  assert.deepEqual(TabDataStore.getTab(store, "pending"), {
    items: [],
    hasMore: false,
    total: 0,
    offset: 0,
    error: null,
  });
});

test("TabDataStore.setPage replaces one tab without mutating siblings", () => {
  const store = TabDataStore.create();
  const next = TabDataStore.setPage(store, "pending", {
    items: [{ upload_id: 1 }],
    hasMore: true,
    total: 10,
    offset: 0,
  });

  assert.notEqual(next, store);
  assert.notEqual(next.pending, store.pending);
  assert.equal(next.submitted, store.submitted);
  assert.deepEqual(TabDataStore.getTab(next, "pending"), {
    items: [{ upload_id: 1 }],
    hasMore: true,
    total: 10,
    offset: 0,
    error: null,
  });
});

test("TabDataStore.appendPage appends items and updates pagination metadata", () => {
  const seeded = TabDataStore.setPage(TabDataStore.create(), "failed", {
    items: [{ upload_id: 7 }],
    hasMore: true,
    total: 4,
    offset: 0,
  });

  const next = TabDataStore.appendPage(seeded, "failed", {
    items: [{ upload_id: 8 }, { upload_id: 9 }],
    hasMore: false,
    total: 4,
    offset: 50,
  });

  assert.deepEqual(TabDataStore.getTab(next, "failed"), {
    items: [{ upload_id: 7 }, { upload_id: 8 }, { upload_id: 9 }],
    hasMore: false,
    total: 4,
    offset: 50,
    error: null,
  });
  assert.deepEqual(TabDataStore.getTab(seeded, "failed").items, [{ upload_id: 7 }]);
});

test("TabDataStore.setError preserves pagination data and clears only the error field", () => {
  const seeded = TabDataStore.setPage(TabDataStore.create(), "submitted", {
    items: [{ upload_id: 11 }],
    hasMore: true,
    total: 99,
    offset: 50,
  });

  const next = TabDataStore.setError(seeded, "submitted", "boom");

  assert.deepEqual(TabDataStore.getTab(next, "submitted"), {
    items: [{ upload_id: 11 }],
    hasMore: true,
    total: 99,
    offset: 50,
    error: "boom",
  });
});
