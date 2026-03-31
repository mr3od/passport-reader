const test = require("node:test");
const assert = require("node:assert/strict");

const { getNotificationTitle, NOTIFICATION_TYPES } = require("../notifications.js");

test("getNotificationTitle uses a generic context-change title by default", () => {
  assert.equal(
    getNotificationTitle(NOTIFICATION_TYPES.CONTEXT_CHANGE),
    "تم رصد تغيير جديد في الحساب أو العقد",
  );
});
