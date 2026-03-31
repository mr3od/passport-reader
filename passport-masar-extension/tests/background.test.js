const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildContractSnapshotUpdate,
  shouldSubmitRecord,
  countFailedRecords,
  hasValidSessionSyncSignal,
  shouldStopBatchAfterResult,
} = require("../background.js");

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

test("buildContractSnapshotUpdate clears stale contract selection when selected contract disappears", () => {
  const update = buildContractSnapshotUpdate(
    [{ contractId: 9, contractStatus: { id: 0 }, companyNameAr: "x" }],
    "42",
  );
  assert.equal(update.masar_contract_id, "");
  assert.equal(update.masar_contract_state, "unknown");
});

test("hasValidSessionSyncSignal requires a real session marker", () => {
  assert.equal(hasValidSessionSyncSignal(null), false);
  assert.equal(hasValidSessionSyncSignal({}), false);
  assert.equal(hasValidSessionSyncSignal({ entityId: null, jwt: null }), false);
  assert.equal(hasValidSessionSyncSignal({ entityId: "819868", jwt: null }), true);
  assert.equal(hasValidSessionSyncSignal({ entityId: "", jwt: "Bearer abc" }), true);
});
