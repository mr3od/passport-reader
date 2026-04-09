const test = require("node:test");
const assert = require("node:assert/strict");

const {
  filterServerSections,
  mergeOptimisticSections,
  normalizeBatchState,
} = require("../queue-filter.js");

test("filterServerSections preserves server tab payloads without reclassification", () => {
  const sections = filterServerSections({
    pending: [{ upload_id: 1 }, { upload_id: 2 }],
    submitted: [{ upload_id: 3 }],
    failed: [{ upload_id: 4 }, { upload_id: 5 }],
  });

  assert.deepEqual(sections.pending.map((record) => record.upload_id), [1, 2]);
  assert.deepEqual(sections.submitted.map((record) => record.upload_id), [3]);
  assert.deepEqual(sections.failed.map((record) => record.upload_id), [4, 5]);
});

test("mergeOptimisticSections moves queued pending rows into in-progress", () => {
  const sections = mergeOptimisticSections({
    serverSections: {
      pending: [{ upload_id: 1 }, { upload_id: 2 }],
      submitted: [{ upload_id: 3 }],
      failed: [{ upload_id: 4 }],
    },
    batchState: {
      queue: [2],
      active_id: 2,
      results: {},
      blocked_reason: null,
    },
    activeSubmitId: null,
  });

  assert.deepEqual(sections.pending.map((record) => record.upload_id), [1]);
  assert.deepEqual(sections.inProgress.map((record) => record.upload_id), [2]);
  assert.deepEqual(sections.submitted.map((record) => record.upload_id), [3]);
  assert.deepEqual(sections.failed.map((record) => record.upload_id), [4]);
});

test("mergeOptimisticSections shows retried failed rows in progress while queued", () => {
  const sections = mergeOptimisticSections({
    serverSections: {
      pending: [],
      submitted: [],
      failed: [{ upload_id: 9 }],
    },
    batchState: {
      queue: [9],
      active_id: 9,
      results: {},
      blocked_reason: null,
    },
    activeSubmitId: null,
  });

  assert.deepEqual(sections.inProgress.map((record) => record.upload_id), [9]);
  assert.deepEqual(sections.failed.map((record) => record.upload_id), []);
});

test("mergeOptimisticSections moves completed optimistic rows into submitted and failed sections", () => {
  const sections = mergeOptimisticSections({
    serverSections: {
      pending: [{ upload_id: 1 }, { upload_id: 2 }, { upload_id: 3 }],
      submitted: [{ upload_id: 4 }],
      failed: [{ upload_id: 5 }],
    },
    batchState: {
      queue: [1, 2, 3],
      active_id: 3,
      results: {
        1: "submitted",
        2: "failed",
      },
      blocked_reason: null,
    },
    activeSubmitId: null,
  });

  assert.deepEqual(sections.pending.map((record) => record.upload_id), []);
  assert.deepEqual(sections.inProgress.map((record) => record.upload_id), [3]);
  assert.deepEqual(sections.submitted.map((record) => record.upload_id), [4, 1]);
  assert.deepEqual(sections.failed.map((record) => record.upload_id), [5, 2]);
});

test("mergeOptimisticSections prefers fresher submitted data over stale pending duplicates", () => {
  const sections = mergeOptimisticSections({
    serverSections: {
      pending: [{ upload_id: 12, masar_status: null }],
      submitted: [{ upload_id: 12, masar_status: "submitted" }],
      failed: [],
    },
    batchState: {
      queue: [],
      active_id: null,
      results: {},
      blocked_reason: null,
    },
    activeSubmitId: null,
  });

  assert.deepEqual(sections.pending.map((record) => record.upload_id), []);
  assert.deepEqual(sections.submitted.map((record) => record.upload_id), [12]);
});

test("normalizeBatchState derives in-progress ids from deterministic queue and results", () => {
  const normalized = normalizeBatchState(
    {
      queue: [1, 2, 3],
      active_id: 3,
      results: {
        1: "submitted",
        2: "missing",
      },
      blocked_reason: null,
    },
    null,
  );

  assert.equal(normalized.activeId, 3);
  assert.deepEqual([...normalized.inProgressIds], [3]);
  assert.deepEqual([...normalized.submittedIds], [1]);
  assert.deepEqual([...normalized.failedIds], [2]);
});
