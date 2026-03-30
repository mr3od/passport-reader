const test = require("node:test");
const assert = require("node:assert/strict");

const { classifyFailure } = require("../popup-failure.js");

test("classifyFailure maps backend 401 status to relink", () => {
  assert.deepEqual(classifyFailure({ ok: false, status: 401 }), { type: "relink" });
});

test("classifyFailure maps tagged backend auth failures to relink", () => {
  assert.deepEqual(
    classifyFailure({ ok: false, failureKind: "backend-auth", error: "فشل تحديث الحالة (401)" }),
    { type: "relink" },
  );
});

test("classifyFailure maps tagged masar auth failures to masar login", () => {
  assert.deepEqual(
    classifyFailure({ ok: false, failureKind: "masar-auth", error: "فشل قراءة الجواز (401)" }),
    { type: "masar-login" },
  );
});

test("classifyFailure leaves unrelated failures generic", () => {
  assert.deepEqual(
    classifyFailure({ ok: false, status: 403, error: "هذا الحساب موقوف" }),
    { type: "generic" },
  );
});
