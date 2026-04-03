const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildBatchBannerState,
  buildDisplayName,
  buildOptimisticCounts,
  ensureActionContextState,
  getRecordNote,
  getScreenTheme,
  renderHomeSummary,
  handleCardClick,
  handleSubmitResponse,
  handleContractSelectionChange,
  getSubmissionContextMismatch,
  getSubmissionContextMismatchToast,
  setDetailLinkLoadingState,
  showToast,
  shouldRefreshContractsForStorageChange,
  shouldRefreshWorkspaceForStorageChange,
} = require("../popup.js");

test("buildBatchBannerState summarizes the richer batch object", () => {
  assert.deepEqual(
    buildBatchBannerState({
      submission_batch: {
        source_total: 23,
        queued_ids: [11, 12, 13],
        active_id: 10,
        submitted_ids: [1, 2, 3, 4, 5, 6, 7, 8],
        blocked_reason: null,
      },
      active_submit_id: 10,
    }),
    {
      visible: true,
      title: "جارٍ رفع الجوازات",
      summary: "تم رفع 8 من 23",
      detail: "جواز واحد جارٍ رفعه و3 في الانتظار",
      blockedReason: null,
    },
  );
});

test("buildDisplayName prefers slim Arabic list names before OCR payloads", () => {
  assert.equal(
    buildDisplayName({
      upload_id: 16,
      full_name_ar: "سارة محمد العتيبي",
      extraction_result: {
        data: {
          GivenNameTokensEn: ["Sarah", "Mohammad"],
          SurnameEn: "Alotaibi",
        },
      },
    }),
    "سارة محمد العتيبي",
  );
});

test("buildDisplayName prefers Arabic passport names when present", () => {
  assert.equal(
    buildDisplayName({
      upload_id: 17,
      extraction_result: {
        data: {
          GivenNameTokensAr: ["سارة", "محمد"],
          SurnameAr: "العتيبي",
          GivenNameTokensEn: ["Sarah", "Mohammad"],
          SurnameEn: "Alotaibi",
        },
      },
    }),
    "سارة محمد العتيبي",
  );
});

test("buildDisplayName falls back to English when Arabic names are missing", () => {
  assert.equal(
    buildDisplayName({
      upload_id: 18,
      extraction_result: {
        data: {
          GivenNameTokensEn: ["Sarah", "Mohammad"],
          SurnameEn: "Alotaibi",
        },
      },
    }),
    "Sarah Mohammad Alotaibi",
  );
});

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

test("buildOptimisticCounts moves queued records from pending into in-progress", () => {
  assert.deepEqual(
    buildOptimisticCounts(
      { pending: 5, submitted: 2, failed: 1 },
      [10, 11],
      12,
    ),
    { pending: 2, inProgress: 3, submitted: 2, failed: 1 },
  );
});

test("buildOptimisticCounts supports the richer batch object shape", () => {
  assert.deepEqual(
    buildOptimisticCounts(
      { pending: 4, submitted: 2, failed: 1 },
      { queued_ids: [10, 11], active_id: 12 },
      null,
    ),
    { pending: 1, inProgress: 3, submitted: 2, failed: 1 },
  );
});

test("handleCardClick delegates mutamer details opening to the background worker", async () => {
  const messages = [];
  global.chrome = {
    runtime: {
      sendMessage: (message, callback) => {
        messages.push(message);
        callback({ ok: true });
      },
    },
  };

  const result = await handleCardClick({ clickUrl: "https://example.com/details/7" });

  assert.equal(result, true);
  assert.deepEqual(messages, [{
    type: "OPEN_MUTAMER_DETAILS_EXPERIMENT",
    clickUrl: "https://example.com/details/7",
    uploadId: null,
    detailsContext: null,
  }]);
  delete global.chrome;
});

test("handleCardClick returns false when the background worker rejects the request", async () => {
  global.chrome = {
    runtime: {
      sendMessage: (_message, callback) => {
        callback({ ok: false });
      },
    },
  };

  const result = await handleCardClick({ clickUrl: "https://example.com/details/7" });

  assert.equal(result, false);
  delete global.chrome;
});

test("handleCardClick shows an Arabic error when the mutamer is missing", async () => {
  let shownError = null;
  global.chrome = {
    runtime: {
      sendMessage: (_message, callback) => {
        callback({ ok: false, errorCode: "mutamer-missing" });
      },
    },
  };

  const result = await handleCardClick({
    clickUrl: "https://example.com/details/7",
    onMissingRecord: (message) => {
      shownError = message;
    },
  });

  assert.equal(result, false);
  assert.equal(shownError, "هذا الجواز غير موجود");
  delete global.chrome;
});

test("handleCardClick shows an Arabic error when the mutamer is inaccessible in the current context", async () => {
  let shownError = null;
  global.chrome = {
    runtime: {
      sendMessage: (_message, callback) => {
        callback({ ok: false, errorCode: "mutamer-inaccessible" });
      },
    },
  };

  const result = await handleCardClick({
    clickUrl: "https://example.com/details/7",
    onInaccessible: (message) => {
      shownError = message;
    },
  });

  assert.equal(result, false);
  assert.equal(shownError, "التفاصيل غير متاحة في الحساب الحالي");
  delete global.chrome;
});

test("showToast writes a transient popup message without changing screens", () => {
  const toast = {
    textContent: "",
    dataset: {},
    classList: {
      hidden: true,
      toggle(_name, hidden) {
        this.hidden = hidden;
      },
      add() {
        this.hidden = true;
      },
    },
  };
  global.document = {
    getElementById(id) {
      return id === "app-toast" ? toast : null;
    },
  };

  showToast("جارٍ فتح التفاصيل...", { durationMs: 0 });

  assert.equal(toast.textContent, "جارٍ فتح التفاصيل...");
  assert.equal(toast.dataset.tone, "neutral");
  assert.equal(toast.classList.hidden, false);
  delete global.document;
});

test("setDetailLinkLoadingState toggles submitted card loading label and disabled state", () => {
  const link = {
    textContent: "عرض التفاصيل",
    dataset: {},
    attributes: {},
    classList: {
      values: new Set(),
      add(value) {
        this.values.add(value);
      },
      remove(value) {
        this.values.delete(value);
      },
      contains(value) {
        return this.values.has(value);
      },
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
  };

  setDetailLinkLoadingState(link, true, "عرض التفاصيل");
  assert.equal(link.textContent, "جارٍ فتح التفاصيل...");
  assert.equal(link.dataset.loading, "true");
  assert.equal(link.dataset.originalLabel, "عرض التفاصيل");
  assert.equal(link.attributes["aria-disabled"], "true");
  assert.equal(link.classList.contains("muted"), true);

  setDetailLinkLoadingState(link, false, "عرض التفاصيل");
  assert.equal(link.textContent, "عرض التفاصيل");
  assert.equal(link.dataset.loading, undefined);
  assert.equal(link.attributes["aria-disabled"], "false");
  assert.equal(link.classList.contains("muted"), false);
});

test("getSubmissionContextMismatch flags a different entity before contract", () => {
  const mismatch = getSubmissionContextMismatch(
    {
      masar_status: "submitted",
      submission_entity_id: "819868",
      submission_contract_id: "222452",
    },
    {
      masar_entity_id: "819455",
      masar_contract_id: "999999",
    },
  );

  assert.equal(mismatch, "entity");
});

test("getSubmissionContextMismatch flags a different contract for submitted mutamers", () => {
  const mismatch = getSubmissionContextMismatch(
    {
      masar_status: "submitted",
      submission_entity_id: "819868",
      submission_contract_id: "222452",
    },
    {
      masar_entity_id: "819868",
      masar_contract_id: "111111",
    },
  );

  assert.equal(mismatch, "contract");
});

test("getSubmissionContextMismatchToast maps entity and contract mismatches to precise Arabic guidance", () => {
  assert.equal(getSubmissionContextMismatchToast("entity"), "افتح الحساب الذي تم الرفع منه");
  assert.equal(getSubmissionContextMismatchToast("contract"), "افتح العقد الذي تم الرفع منه");
});

test("ensureActionContextState requires contract confirmation before gated actions", () => {
  const requirement = ensureActionContextState({
    activeUiContext: {
      requires_contract_confirmation: true,
      requires_group_confirmation: false,
      contract_id: null,
      group_id: null,
      available_groups: [],
    },
    selectedContractId: null,
  });

  assert.deepEqual(requirement, {
    ok: false,
    reason: "contract",
  });
});

test("ensureActionContextState blocks actions when the selected contract is inactive", () => {
  const requirement = ensureActionContextState({
    activeUiContext: {
      requires_contract_confirmation: false,
      requires_group_confirmation: false,
      contract_id: "223664",
      contract_state: "inactive",
      group_id: null,
      available_groups: [],
    },
    selectedContractId: "223664",
  });

  assert.deepEqual(requirement, {
    ok: false,
    reason: "contract-inactive",
  });
});

test("ensureActionContextState ignores group readiness for the current workflow", () => {
  const requirement = ensureActionContextState({
    activeUiContext: {
      requires_contract_confirmation: false,
      requires_group_confirmation: true,
      contract_id: "223664",
      group_id: null,
      available_groups: [{ id: "group-1" }],
    },
    selectedContractId: "223664",
  });

  assert.deepEqual(requirement, {
    ok: true,
    reason: null,
  });
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

test("handleContractSelectionChange writes the selected contract without forcing sync", async () => {
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

  assert.deepEqual(stored, { masar_contract_id: "42" });
  assert.equal(reloaded, true);
});

test("getRecordNote maps stored failure reason text to Arabic when no code is present", () => {
  assert.equal(
    getRecordNote({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
      failure_reason_code: null,
      failure_reason_text: "Passport image is not clear",
      _section: "failed",
    }),
    "صورة الجواز غير واضحة",
  );
});

test("getRecordNote hides unknown raw failure text behind the generic failed label", () => {
  assert.equal(
    getRecordNote({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
      failure_reason_code: null,
      failure_reason_text: "Unexpected remote failure",
      _section: "failed",
    }),
    "فشل",
  );
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

test("shouldRefreshWorkspaceForStorageChange refreshes for active ui context updates", () => {
  const shouldRefresh = shouldRefreshWorkspaceForStorageChange({
    areaName: "local",
    changes: {
      active_ui_context: {
        oldValue: null,
        newValue: { entity_id: "820456" },
      },
    },
    isMainScreenVisible: true,
  });

  assert.equal(shouldRefresh, true);
});

test("shouldRefreshWorkspaceForStorageChange ignores contract-only local updates for contract refetch decisions", () => {
  const shouldRefresh = shouldRefreshWorkspaceForStorageChange({
    areaName: "local",
    changes: {
      masar_contract_id: {
        oldValue: "1",
        newValue: "2",
      },
    },
    isMainScreenVisible: true,
  });

  assert.equal(shouldRefresh, true);
});

test("shouldRefreshContractsForStorageChange only reacts to entity or auth/session boundary changes", () => {
  assert.equal(
    shouldRefreshContractsForStorageChange("local", {
      masar_contract_id: { oldValue: "1", newValue: "2" },
      active_ui_context: { oldValue: {}, newValue: {} },
    }),
    false,
  );
  assert.equal(
    shouldRefreshContractsForStorageChange("local", {
      masar_entity_id: { oldValue: "1", newValue: "2" },
    }),
    true,
  );
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
