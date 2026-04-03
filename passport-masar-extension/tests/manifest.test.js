const test = require("node:test");
const assert = require("node:assert/strict");

const manifest = require("../manifest.json");

test("manifest removes passive content scripts and webRequest permission", () => {
  assert.deepEqual(manifest.content_scripts || [], []);
  assert.equal((manifest.permissions || []).includes("webRequest"), false);
});
