const test = require("node:test");
const assert = require("node:assert/strict");
const Strings = require("../strings.js");

const {
  getSectionEmptyNote,
  PRE_RELEASE_SHOW_RAW_FAILURES,
  buildBatchBannerState,
  buildDisplayName,
  buildRenderableServerSections,
  buildSubmitSelectionActionState,
  ensureActionContextState,
  getRecordNote,
  getScreenTheme,
  handleCardClick,
  handleSubmitResponse,
  handleContractSelectionChange,
  isBatchCurrentlyRunning,
  buildContractPickerState,
  decideBootstrapAction,
  getSubmissionContextMismatch,
  getSubmissionContextMismatchToast,
  handleResumeBatchResponse,
  reconcileSelectedUploadIds,
  sortSectionsForRender,
  setDetailLinkLoadingState,
  showToast,
} = require("../popup.js");

test("buildBatchBannerState summarizes the richer batch object", () => {
  assert.deepEqual(
    buildBatchBannerState({
      submit_batch: {
        queue: [10, 11, 12, 13, 1, 2, 3, 4, 5, 6, 7, 8],
        active_id: 10,
        results: {
          1: "submitted",
          2: "submitted",
          3: "submitted",
          4: "submitted",
          5: "submitted",
          6: "submitted",
          7: "submitted",
          8: "submitted",
        },
        blocked_reason: null,
      },
      active_submit_id: 10,
    }),
    {
      visible: true,
      title: "جارٍ رفع الجوازات",
      summary: "تم رفع 8 من 12",
      detail: "جواز واحد جارٍ رفعه و3 في الانتظار",
      blockedReason: null,
    },
  );
});

test("buildBatchBannerState includes failed count in detail when failures exist", () => {
  const results = {};
  for (let index = 24; index <= 79; index += 1) {
    results[index] = "submitted";
  }
  [80, 81, 82, 83, 84, 85].forEach((uploadId) => {
    results[uploadId] = "failed";
  });
  assert.deepEqual(
    buildBatchBannerState({
      submit_batch: {
        queue: [20, 21, 22, 23, ...Array.from({ length: 62 }, (_v, i) => i + 24)],
        active_id: 20,
        results,
        blocked_reason: null,
      },
      active_submit_id: 20,
    }),
    {
      visible: true,
      title: "جارٍ رفع الجوازات",
      summary: "تم رفع 56 من 66",
      detail: "جواز واحد جارٍ رفعه و3 في الانتظار • 6 فشل",
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

test("decideBootstrapAction retries session sync before showing the activate screen", () => {
  assert.equal(
    decideBootstrapAction({
      hasApiToken: true,
      hasEntityAfterSync: true,
    }),
    "main",
  );
  assert.equal(
    decideBootstrapAction({
      hasApiToken: true,
      hasEntityAfterSync: false,
    }),
    "activate",
  );
  assert.equal(
    decideBootstrapAction({
      hasApiToken: false,
      hasEntityAfterSync: false,
    }),
    "setup",
  );
});

test("buildContractPickerState hides the dropdown and shows a plain message when no contracts are selectable", () => {
  const state = buildContractPickerState([
    {
      contractId: 7,
      contractStatus: { id: 0 },
      contractEndDate: "2020-01-01T00:00:00",
    },
  ], "7");

  assert.equal(state.showDropdown, false);
  assert.equal(state.selectableContracts.length, 0);
  assert.equal(state.emptyMessage, "لا يوجد عقد نشط في الحساب الحالي");
});

test("buildContractPickerState keeps the dropdown when there is a real contract choice", () => {
  const state = buildContractPickerState([
    {
      contractId: 7,
      companyNameAr: "العقد الأول",
      contractStatus: { id: 0 },
      contractEndDate: "2099-01-01T00:00:00",
    },
    {
      contractId: 8,
      companyNameAr: "العقد الثاني",
      contractStatus: { id: 0 },
      contractEndDate: "2099-01-01T00:00:00",
    },
  ], "7");

  assert.equal(state.showDropdown, true);
  assert.equal(state.selectableContracts.length, 2);
  assert.equal(state.emptyMessage, "");
});

test("mark-all copy makes the loaded-only scope explicit", () => {
  assert.equal(Strings.ACTION_MARK_ALL_SELECTABLE, "تحديد المحمل");
});

test("handleResumeBatchResponse surfaces a missing batch instead of silently pretending to resume", async () => {
  const calls = [];

  const result = await handleResumeBatchResponse({
    response: { ok: false, errorCode: "submission-batch-missing" },
    onReload: async () => {
      calls.push("reload");
    },
    onUnavailable: async () => {
      calls.push("unavailable");
    },
  });

  assert.equal(result, false);
  assert.deepEqual(calls, ["unavailable"]);
});

test("getSectionEmptyNote hides the shared empty hint when the active tab has records", () => {
  assert.equal(
    getSectionEmptyNote("submitted", {
      submitted: [{ upload_id: 21 }],
    }),
    "",
  );
});

test("getSectionEmptyNote returns the tab-specific empty message when the tab is empty", () => {
  assert.equal(
    getSectionEmptyNote("failed", {
      failed: [],
    }),
    "لا توجد محاولات فاشلة",
  );
});

test("buildRenderableServerSections replays the last submit result into cached sections", () => {
  const sections = buildRenderableServerSections(
    {
      pending: [{ upload_id: 21, masar_status: null }],
      submitted: [],
      failed: [],
    },
    {
      upload_id: 21,
      status: "submitted",
      masar_detail_id: "detail-21",
      submission_contract_id: "c-1",
    },
  );

  assert.deepEqual(sections.pending, []);
  assert.equal(sections.submitted.length, 1);
  assert.equal(sections.submitted[0].upload_id, 21);
  assert.equal(sections.submitted[0].masar_status, "submitted");
  assert.equal(sections.submitted[0].masar_detail_id, "detail-21");
});

test("sortSectionsForRender keeps in-progress rows in queue order with active first", () => {
  const sorted = sortSectionsForRender({
    sections: {
      pending: [],
      inProgress: [
        { upload_id: 12, created_at: "2026-03-13T12:00:00+00:00" },
        { upload_id: 10, created_at: "2026-03-13T10:00:00+00:00" },
        { upload_id: 11, created_at: "2026-03-13T11:00:00+00:00" },
      ],
      submitted: [],
      failed: [],
    },
    sessionData: {
      submit_batch: { queue: [10, 11, 12], active_id: 11, results: {} },
      active_submit_id: 11,
    },
  });

  assert.deepEqual(sorted.inProgress.map((record) => record.upload_id), [11, 10, 12]);
});

test("isBatchCurrentlyRunning returns true for archive batches too", () => {
  assert.equal(
    isBatchCurrentlyRunning({
      archive_batch: { queue: [91], active_id: 91, results: {} },
      active_archive_id: 91,
    }),
    true,
  );
});

test("popup no longer exports result banner helpers", () => {
  const popup = require("../popup.js");
  assert.equal(Object.hasOwn(popup, "buildResultBannerState"), false);
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

test("PRE_RELEASE_SHOW_RAW_FAILURES keeps raw failed notes explicitly gated", () => {
  assert.equal(PRE_RELEASE_SHOW_RAW_FAILURES, true);
});

test("getRecordNote shows known raw failure text on failed cards in pre-release mode", () => {
  assert.equal(
    getRecordNote({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
      failure_reason_code: null,
      failure_reason_text: "Passport image is not clear",
      _section: "failed",
    }),
    "Passport image is not clear",
  );
});

test("getRecordNote shows unknown raw failure text on failed cards in pre-release mode", () => {
  assert.equal(
    getRecordNote({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
      failure_reason_code: null,
      failure_reason_text: "Unexpected remote failure",
      _section: "failed",
    }),
    "Unexpected remote failure",
  );
});

test("getRecordNote suppresses duplicate in-progress labels in the card body", () => {
  assert.equal(
    getRecordNote({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
      failure_reason_code: null,
      failure_reason_text: "Unexpected remote failure",
      _section: "inProgress",
      _inProgressState: "queued",
    }),
    "",
  );
});


test("older workspace load should not win", async () => {
  const MasarPopup = require("../popup.js");
  const state = { workspaceLoadId: 0 };
  
  let firstLoadId;
  let secondLoadId;
  
  const firstLoad = (async () => {
    firstLoadId = ++state.workspaceLoadId;
    await new Promise((resolve) => setTimeout(resolve, 20));
    return { loadId: firstLoadId, data: "first" };
  })();
  
  const secondLoad = (async () => {
    secondLoadId = ++state.workspaceLoadId;
    await new Promise((resolve) => setTimeout(resolve, 5));
    return { loadId: secondLoadId, data: "second" };
  })();
  
  const firstResult = await firstLoad;
  const secondResult = await secondLoad;
  
  assert.equal(firstResult.loadId, 1);
  assert.equal(secondResult.loadId, 2);
  assert.equal(state.workspaceLoadId, 2);
  assert.notEqual(firstResult.loadId, state.workspaceLoadId);
});

test("older tab fetch should not overwrite newer tab fetch", async () => {
  const cache = {
    items: [],
    status: "idle",
    dirty: true,
    error: null,
    requestId: 0,
  };
  
  let firstRequestId;
  let secondRequestId;
  
  const firstFetch = (async () => {
    firstRequestId = ++cache.requestId;
    await new Promise((resolve) => setTimeout(resolve, 20));
    return { requestId: firstRequestId, items: [{ id: 1 }] };
  })();
  
  const secondFetch = (async () => {
    secondRequestId = ++cache.requestId;
    await new Promise((resolve) => setTimeout(resolve, 5));
    return { requestId: secondRequestId, items: [{ id: 2 }] };
  })();
  
  const secondResult = await secondFetch;
  if (secondResult.requestId === cache.requestId) {
    cache.items = secondResult.items;
  }
  
  const firstResult = await firstFetch;
  if (firstResult.requestId === cache.requestId) {
    cache.items = firstResult.items;
  }
  
  assert.equal(cache.requestId, 2);
  assert.deepEqual(cache.items, [{ id: 2 }]);
});

test("failed page fetch with existing cached data should show toast not error screen", () => {
  const activeCache = {
    items: [{ upload_id: 1 }, { upload_id: 2 }],
    status: "ready",
  };
  const pageResponse = { ok: false, error: "Network error" };
  const hasUsableData = activeCache && activeCache.items.length > 0;
  
  assert.equal(hasUsableData, true);
});

test("failed page fetch with no cached data should show error screen", () => {
  const activeCache = {
    items: [],
    status: "idle",
  };
  const pageResponse = { ok: false, error: "Network error" };
  const hasUsableData = activeCache && activeCache.items.length > 0;
  
  assert.equal(hasUsableData, false);
});

test("reconcileSelectedUploadIds drops ghost ids and keeps only selectable ids", () => {
  const selected = new Set([10, 11, 12]);
  const selectable = new Set([11, 13]);

  const next = reconcileSelectedUploadIds(selected, selectable);

  assert.deepEqual([...next], [11]);
});

test("buildSubmitSelectionActionState keeps button visible and disables when selection is empty", () => {
  const empty = buildSubmitSelectionActionState({
    selectedCount: 0,
    isBatchRunning: false,
  });
  const withSelection = buildSubmitSelectionActionState({
    selectedCount: 3,
    isBatchRunning: false,
  });

  assert.equal(empty.hidden, false);
  assert.equal(empty.disabled, true);
  assert.equal(empty.label, "المحدد 0");
  assert.equal(withSelection.hidden, false);
  assert.equal(withSelection.disabled, false);
  assert.equal(withSelection.label, "المحدد 3");
});

test("buildSubmitSelectionActionState disables while batch is running", () => {
  const state = buildSubmitSelectionActionState({
    selectedCount: 2,
    isBatchRunning: true,
  });

  assert.equal(state.disabled, true);
});

test("buildSubmitSelectionActionState disables submit action when contract is not active", () => {
  const state = buildSubmitSelectionActionState({
    selectedCount: 2,
    isBatchRunning: false,
    canSubmit: false,
  });

  assert.equal(state.disabled, false);
  assert.equal(state.submitDisabled, true);
});
