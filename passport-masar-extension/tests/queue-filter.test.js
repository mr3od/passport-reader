const test = require("node:test");
const assert = require("node:assert/strict");

const { filterQueueSections } = require("../queue-filter.js");

test("filterQueueSections splits records into pending, in-progress, submitted, and failed", () => {
  const records = [
    { upload_id: 1, upload_status: "processed", masar_status: null },
    { upload_id: 2, upload_status: "processed", masar_status: null },
    { upload_id: 3, upload_status: "processed", masar_status: "submitted" },
    { upload_id: 4, upload_status: "processed", masar_status: "failed" },
    { upload_id: 5, upload_status: "failed", masar_status: null },
  ];

  const sections = filterQueueSections(records, new Set([2]));

  assert.deepEqual(sections.pending.map((record) => record.upload_id), [1]);
  assert.deepEqual(sections.inProgress.map((record) => record.upload_id), [2]);
  assert.deepEqual(sections.submitted.map((record) => record.upload_id), [3]);
  assert.deepEqual(sections.failed.map((record) => record.upload_id), [4, 5]);
});
