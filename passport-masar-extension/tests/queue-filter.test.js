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
    batchState: [2],
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
    batchState: [9],
    activeSubmitId: null,
  });

  assert.deepEqual(sections.inProgress.map((record) => record.upload_id), [9]);
  assert.deepEqual(sections.failed.map((record) => record.upload_id), []);
});

test("normalizeBatchState supports the current array batch shape and active submit id", () => {
  const normalized = normalizeBatchState([1, 2], 3);

  assert.equal(normalized.activeId, 3);
  assert.deepEqual([...normalized.inProgressIds], [1, 2, 3]);
});
