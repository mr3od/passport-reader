const test = require("node:test");
const assert = require("node:assert/strict");

const { shouldSubmitRecord, countFailedRecords, shouldStopBatchAfterResult } = require("../background.js");

test("shouldSubmitRecord allows processed records that still need review", () => {
  assert.equal(
    shouldSubmitRecord({
      upload_status: "processed",
      masar_status: null,
      review_status: "needs_review",
    }),
    true,
  );
});

test("shouldSubmitRecord allows retries for failed Masar submissions", () => {
  assert.equal(
    shouldSubmitRecord({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
    }),
    true,
  );
});

test("countFailedRecords includes processing failures and Masar failures", () => {
  assert.equal(
    countFailedRecords([
      { upload_status: "failed", masar_status: null },
      { upload_status: "processed", masar_status: "failed" },
      { upload_status: "processed", masar_status: "submitted" },
    ]),
    2,
  );
});

test("shouldStopBatchAfterResult aborts the batch when auth recovery is needed", () => {
  assert.equal(shouldStopBatchAfterResult({ ok: false, failureKind: "backend-auth" }), true);
  assert.equal(shouldStopBatchAfterResult({ ok: false, failureKind: "masar-auth" }), true);
  assert.equal(shouldStopBatchAfterResult({ ok: false, failureKind: null }), false);
});
