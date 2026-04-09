const test = require("node:test");
const assert = require("node:assert/strict");

const { getStatusColor, getStatusLabel } = require("../status.js");

test("getStatusLabel returns amber submitted label for submitted records needing review", () => {
  assert.equal(
    getStatusLabel({
      upload_status: "processed",
      masar_status: "submitted",
      review_status: "needs_review",
      inProgress: false,
    }),
    "تم الرفع - يحتاج مراجعة",
  );
});

test("getStatusLabel distinguishes active and queued in-progress records", () => {
  assert.equal(
    getStatusLabel({
      upload_status: "processed",
      masar_status: null,
      review_status: "auto",
      inProgress: "active",
    }),
    "جاري الرفع",
  );
  assert.equal(
    getStatusLabel({
      upload_status: "processed",
      masar_status: null,
      review_status: "auto",
      inProgress: "queued",
    }),
    "في الانتظار",
  );
});

test("getStatusLabel returns missing label for records removed remotely", () => {
  assert.equal(
    getStatusLabel({
      upload_status: "processed",
      masar_status: "missing",
      review_status: "auto",
      inProgress: false,
    }),
    "غير موجود",
  );
});

test("getStatusLabel and color prefer in-progress state over stale failed status during retry", () => {
  assert.equal(
    getStatusLabel({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
      inProgress: "queued",
    }),
    "في الانتظار",
  );
  assert.equal(
    getStatusColor({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
      inProgress: "queued",
    }),
    "#5D6879",
  );
});
