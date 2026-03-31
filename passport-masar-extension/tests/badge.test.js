const test = require("node:test");
const assert = require("node:assert/strict");

const { computeBadgeState } = require("../badge.js");

test("computeBadgeState prioritizes session expiry over everything else", () => {
  assert.deepEqual(
    computeBadgeState({
      sessionExpired: true,
      contextChangePending: true,
      failedCount: 9,
    }),
    { text: "!", color: "#D32F2F", priority: 1 },
  );
});

test("computeBadgeState shows failed count when there is no higher-priority alert", () => {
  assert.deepEqual(
    computeBadgeState({
      sessionExpired: false,
      contextChangePending: false,
      failedCount: 3,
    }),
    { text: "3", color: "#D32F2F", priority: 3 },
  );
});
