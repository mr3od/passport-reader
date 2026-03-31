const test = require("node:test");
const assert = require("node:assert/strict");

const {
  getScreenTheme,
  renderHomeSummary,
  handleCardClick,
  handleSubmitResponse,
  handleContractSelectionChange,
  shouldRefreshWorkspaceForStorageChange,
} = require("../popup.js");

test("getScreenTheme maps popup screens to proposal-aligned visual tones", () => {
  assert.deepEqual(getScreenTheme("setup"), {
    tone: "amber",
    surface: "editorial",
  });
  assert.deepEqual(getScreenTheme("activate"), {
    tone: "green",
    surface: "editorial",
  });
  assert.deepEqual(getScreenTheme("session-expired"), {
    tone: "red",
    surface: "editorial",
  });
  assert.deepEqual(getScreenTheme("main"), {
    tone: "olive",
    surface: "workspace",
  });
});

test("renderHomeSummary updates pending and failed counters", () => {
  const pending = { textContent: "" };
  const failed = { textContent: "", dataset: {} };
  const document = {
    getElementById(id) {
      if (id === "pending-count") return pending;
      if (id === "failed-count") return failed;
      return null;
    },
  };

  renderHomeSummary(document, { pendingCount: 5, failedCount: 2 });

  assert.equal(pending.textContent, "5");
  assert.equal(failed.textContent, "2");
  assert.equal(failed.dataset.tone, "danger");
});

test("handleCardClick opens a details tab when a click URL is available", async () => {
  let openedUrl = null;
  global.chrome = {
    tabs: {
      create: async ({ url }) => {
        openedUrl = url;
      },
    },
  };

  await handleCardClick({ clickUrl: "https://example.com/details/7" });

  assert.equal(openedUrl, "https://example.com/details/7");
  delete global.chrome;
});

test("handleSubmitResponse returns relink for backend auth failures", async () => {
  const action = await handleSubmitResponse({
    response: { ok: false, failureKind: "backend-auth" },
    classifyFailure: () => ({ type: "relink" }),
    onRelinkRequired: async () => "relinked",
    onMasarLoginRequired: async () => "login",
    onReload: async () => "reload",
  });

  assert.equal(action, "relinked");
});

test("handleSubmitResponse keeps batch errors from being swallowed", async () => {
  const action = await handleSubmitResponse({
    response: { ok: false, error: "broken" },
    classifyFailure: () => ({ type: "generic" }),
    onRelinkRequired: async () => "relinked",
    onMasarLoginRequired: async () => "login",
    onReload: async () => "reload",
  });

  assert.equal(action, "reload");
});

test("handleContractSelectionChange writes a manual override without forcing sync", async () => {
  let stored = null;
  let reloaded = false;

  await handleContractSelectionChange({
    value: "42",
    writeSelection: async (payload) => {
      stored = payload;
    },
    reloadWorkspace: async () => {
      reloaded = true;
    },
  });

  assert.deepEqual(stored, {
    masar_contract_id: "42",
    masar_contract_manual_override: true,
  });
  assert.equal(reloaded, true);
});

test("shouldRefreshWorkspaceForStorageChange ignores unrelated local cache updates", () => {
  const shouldRefresh = shouldRefreshWorkspaceForStorageChange({
    areaName: "local",
    changes: {
      masar_groups_cache: {
        oldValue: null,
        newValue: { response: { data: { content: [] } } },
      },
    },
    isMainScreenVisible: true,
  });

  assert.equal(shouldRefresh, false);
});

test("shouldRefreshWorkspaceForStorageChange refreshes for visible workspace state updates", () => {
  const shouldRefresh = shouldRefreshWorkspaceForStorageChange({
    areaName: "session",
    changes: {
      submission_batch: {
        oldValue: [],
        newValue: ["u1"],
      },
    },
    isMainScreenVisible: true,
  });

  assert.equal(shouldRefresh, true);
});
