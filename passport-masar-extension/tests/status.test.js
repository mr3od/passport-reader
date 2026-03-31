const test = require("node:test");
const assert = require("node:assert/strict");

const { getStatusLabel } = require("../status.js");

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
