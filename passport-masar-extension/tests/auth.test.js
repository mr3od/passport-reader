const test = require("node:test");
const assert = require("node:assert/strict");

const { exchangeTempToken, normalizeBaseUrl } = require("../auth.js");

test("normalizeBaseUrl trims trailing slashes", () => {
  assert.equal(normalizeBaseUrl("https://passport-api.mr3od.dev///"), "https://passport-api.mr3od.dev");
});

test("exchangeTempToken posts temp token and returns session token", async () => {
  let request;
  const result = await exchangeTempToken({
    apiBaseUrl: "https://passport-api.mr3od.dev/",
    tempToken: "temp-token",
    fetchImpl: async (url, options) => {
      request = { url, options };
      return {
        ok: true,
        json: async () => ({
          session_token: "session-token",
        }),
      };
    },
  });

  assert.equal(request.url, "https://passport-api.mr3od.dev/auth/exchange");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.headers["Content-Type"], "application/json");
  assert.equal(request.options.body, JSON.stringify({ token: "temp-token" }));
  assert.deepEqual(result, {
    sessionToken: "session-token",
  });
});

test("exchangeTempToken surfaces API detail on failure", async () => {
  await assert.rejects(
    exchangeTempToken({
      apiBaseUrl: "https://passport-api.mr3od.dev",
      tempToken: "used-token",
      fetchImpl: async () => ({
        ok: false,
        status: 401,
        json: async () => ({ detail: "الرمز مستخدم" }),
      }),
    }),
    /الرمز مستخدم/,
  );
});
