const test = require("node:test");
const assert = require("node:assert/strict");

const {
  appendDiscoveredIds,
  buildPassportImageUpload,
  buildSubmissionBatchState,
  buildContractSnapshotUpdate,
  buildStoredSubmissionContext,
  buildStoredDetailsContextOverride,
  buildStoredCurrentContractValue,
  classifyMutamerDetailsOutcome,
  shouldSubmitRecord,
  extractMutamerDetailId,
  extractMasarContextFromSnapshot,
  formatCookieDebugSummary,
  hasValidSessionSyncSignal,
  resolveMasarRequestContext,
  shouldStopBatchAfterResult,
  handleMessage,
  canRotatePassportImage,
  markRecordMissing,
  normalizeMasarAuthorizationHeader,
  selectMasarAuthToken,
  rankSourceMasarTabs,
  resolveMutamerDetailsOutcomeResult,
  selectSourceMasarTab,
  shouldPersistContractSnapshot,
} = require("../background.js");

test("buildSubmissionBatchState seeds active and queued ids from the first discovery page", () => {
  const batch = buildSubmissionBatchState({
    discoveredIds: [10, 11, 12],
    sourceTotal: 240,
    nextOffset: 100,
  });

  assert.equal(batch.active_id, 10);
  assert.deepEqual(batch.queued_ids, [11, 12]);
  assert.equal(batch.source_total, 240);
  assert.equal(batch.next_offset, 100);
  assert.equal(batch.exhausted_source, false);
});

test("appendDiscoveredIds appends later discovery pages without duplicating queued ids", () => {
  const batch = buildSubmissionBatchState({
    discoveredIds: [10, 11, 12],
    sourceTotal: 240,
    nextOffset: 100,
  });

  const updated = appendDiscoveredIds(
    batch,
    [{ upload_id: 12 }, { upload_id: 13 }, { upload_id: 14 }],
    240,
    200,
  );

  assert.deepEqual(updated.discovered_ids, [10, 11, 12, 13, 14]);
  assert.deepEqual(updated.queued_ids, [11, 12, 13, 14]);
  assert.equal(updated.next_offset, 200);
});

test("buildPassportImageUpload preserves stored mime type and filename", async () => {
  const payload = buildPassportImageUpload(
    {
      filename: "passport.png",
      mime_type: "image/png",
    },
    new Uint8Array([1, 2, 3, 4]).buffer,
  );

  assert.equal(payload.fileName, "passport.png");
  assert.equal(payload.mimeType, "image/png");
  assert.equal(payload.blob.type, "image/png");
  assert.equal(await payload.blob.arrayBuffer().then((buffer) => buffer.byteLength), 4);
});

test("buildPassportImageUpload falls back to jpeg defaults when metadata is missing", () => {
  const payload = buildPassportImageUpload({}, new Uint8Array([1]).buffer);

  assert.equal(payload.fileName, "passport.jpg");
  assert.equal(payload.mimeType, "image/jpeg");
  assert.equal(payload.blob.type, "image/jpeg");
});

test("shouldSubmitRecord allows processed records that still need review", () => {
  assert.equal(
    shouldSubmitRecord({
      upload_status: "processed",
      masar_status: null,
      review_status: "needs_review",
    }),
    true,
  );
});

test("shouldSubmitRecord allows retries for failed Masar submissions", () => {
  assert.equal(
    shouldSubmitRecord({
      upload_status: "processed",
      masar_status: "failed",
      review_status: "auto",
    }),
    true,
  );
});

test("shouldSubmitRecord rejects the fake pending Masar status", () => {
  assert.equal(
    shouldSubmitRecord({
      upload_status: "processed",
      masar_status: "pending",
      review_status: "auto",
    }),
    false,
  );
});

test("shouldSubmitRecord allows retries for missing Masar records", () => {
  assert.equal(
    shouldSubmitRecord({
      upload_status: "processed",
      masar_status: "missing",
      review_status: "auto",
    }),
    true,
  );
});


test("shouldStopBatchAfterResult aborts the batch when auth recovery is needed", () => {
  assert.equal(shouldStopBatchAfterResult({ ok: false, failureKind: "backend-auth" }), true);
  assert.equal(shouldStopBatchAfterResult({ ok: false, failureKind: "masar-auth" }), true);
  assert.equal(shouldStopBatchAfterResult({ ok: false, failureKind: null }), false);
});

test("buildContractSnapshotUpdate clears stale contract selection when selected contract disappears", () => {
  const update = buildContractSnapshotUpdate(
    [{ contractId: 9, contractStatus: { id: 0 }, companyNameAr: "x" }],
    "42",
  );
  assert.equal(update.masar_contract_id, "");
  assert.equal(update.masar_contract_state, "unknown");
});

test("buildContractSnapshotUpdate marks deactivated contracts as inactive", () => {
  const update = buildContractSnapshotUpdate(
    [{
      contractId: 9,
      contractStatus: { id: 2, name: "Cancelled" },
      contractEndDate: "2099-01-01T00:00:00",
      companyNameAr: "x",
    }],
    "9",
  );

  assert.equal(update.masar_contract_state, "inactive");
});

test("canRotatePassportImage reports unavailable when browser image APIs are missing", () => {
  const originalCreateImageBitmap = global.createImageBitmap;
  const originalOffscreenCanvas = global.OffscreenCanvas;
  delete global.createImageBitmap;
  delete global.OffscreenCanvas;

  assert.equal(canRotatePassportImage(), false);

  global.createImageBitmap = originalCreateImageBitmap;
  global.OffscreenCanvas = originalOffscreenCanvas;
});

test("shouldPersistContractSnapshot skips identical snapshot writes", () => {
  const nextSnapshot = {
    masar_contract_id: "224925",
    masar_contract_name_en: "SLFA CO. FOR HAH AND UMRAH",
    masar_contract_name_ar: "شركة سلفا للحج والعمرة",
    masar_contract_number: "14470511",
    masar_contract_end_date: "2026-05-16T00:00:00",
    masar_contract_status_name: "Active",
    masar_contract_state: "active",
  };

  assert.equal(shouldPersistContractSnapshot(nextSnapshot, nextSnapshot), false);
  assert.equal(
    shouldPersistContractSnapshot(nextSnapshot, {
      ...nextSnapshot,
      masar_contract_state: "expired",
    }),
    true,
  );
});

test("resolveMasarRequestContext prefers the frozen batch context over mutable local storage", () => {
  const context = resolveMasarRequestContext(
    {
      entity_id: "823397",
      entity_type_id: "58",
      contract_id: "224925",
      auth_token: "Bearer batch",
    },
    {
      masar_entity_id: "820456",
      masar_entity_type_id: "58",
      masar_contract_id: "223664",
      masar_auth_token: "Bearer ui",
    },
  );

  assert.deepEqual(context, {
    entity_id: "823397",
    entity_type_id: "58",
    contract_id: "224925",
    auth_token: "Bearer batch",
  });
});

test("buildStoredSubmissionContext keeps the persisted contract-only context", () => {
  const context = buildStoredSubmissionContext({
    submission_entity_id: "819868",
    submission_entity_type_id: "58",
    submission_entity_name: "Agency Entity",
    submission_contract_id: "222452",
    submission_contract_name: "Contract A",
  });

  assert.deepEqual(context, {
    submission_entity_id: "819868",
    submission_entity_type_id: "58",
    submission_entity_name: "Agency Entity",
    submission_contract_id: "222452",
    submission_contract_name: "Contract A",
    submission_contract_name_ar: null,
    submission_contract_name_en: null,
    submission_contract_number: null,
    submission_contract_status: null,
    submission_uo_subscription_status_id: null,
  });
});

test("buildStoredCurrentContractValue recreates the minimal currentContract payload", () => {
  assert.deepEqual(
    buildStoredCurrentContractValue({
      submission_contract_id: "224694",
      submission_contract_number: "0025",
      submission_contract_status: true,
      submission_uo_subscription_status_id: 1,
      submission_contract_name_ar: "شركة البشارة",
      submission_contract_name_en: "BESHARAH UNITED",
    }),
    {
      contractNumber: "0025",
      contractId: 224694,
      contractStatus: true,
      uoSubscriptionStatusId: 1,
      companyNameAr: "شركة البشارة",
      companyNameEn: "BESHARAH UNITED",
    },
  );
});

test("buildStoredDetailsContextOverride uses persisted submission context for details access", () => {
  assert.deepEqual(
    buildStoredDetailsContextOverride({
      submission_entity_id: "819868",
      submission_entity_type_id: "58",
      submission_contract_id: "224694",
      submission_contract_number: "0025",
      submission_contract_status: true,
      submission_uo_subscription_status_id: 1,
      submission_contract_name_ar: "شركة البشارة",
      submission_contract_name_en: "BESHARAH UNITED",
    }),
    {
      entityId: "819868",
      entityTypeId: "58",
      contractId: "224694",
      currentContractRaw:
        "{\"contractNumber\":\"0025\",\"contractId\":224694,\"contractStatus\":true,\"uoSubscriptionStatusId\":1,\"companyNameAr\":\"شركة البشارة\",\"companyNameEn\":\"BESHARAH UNITED\"}",
    },
  );
});

test("normalizeMasarAuthorizationHeader strips nested quotes and keeps a single Bearer prefix", () => {
  assert.equal(
    normalizeMasarAuthorizationHeader('Bearer "abc.def.ghi"'),
    "Bearer abc.def.ghi",
  );
  assert.equal(
    normalizeMasarAuthorizationHeader('"raw-token"'),
    "Bearer raw-token",
  );
});

test("selectMasarAuthToken prefers the user token over a conflicting portal token", () => {
  const buildToken = (payload) => `header.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.sig`;

  const selected = selectMasarAuthToken(
    {
      sessionToken: buildToken({
        tokenType: 3,
        defaultEntityId: 797512,
        defaultEntityTypeId: 52,
      }),
      refreshToken: buildToken({ tokenType: 4 }),
      permissionToken: buildToken({ tokenType: 3 }),
      userToken: buildToken({ tokenType: 5 }),
    },
    {
      entityId: "819455",
      entityTypeId: "58",
    },
  );

  assert.equal(selected, "Bearer header.eyJ0b2tlblR5cGUiOjV9.sig");
});

test("formatCookieDebugSummary groups cookies by name with compact previews", () => {
  assert.deepEqual(
    formatCookieDebugSummary([
      {
        name: "cf_clearance",
        domain: ".masar.nusuk.sa",
        path: "/",
        session: false,
        expirationDate: 1775167246,
        value: "abcdefghijklmnopqrstuvwxyz1234567890",
      },
      {
        name: "TS018f93a3",
        domain: "masar.nusuk.sa",
        path: "/",
        session: true,
        expirationDate: null,
        value: "short-cookie",
      },
    ]),
    {
      cf_clearance: {
        present: true,
        domain: ".masar.nusuk.sa",
        path: "/",
        session: false,
        expires: 1775167246,
        valuePreview: "abcdefghijklmnopqrstuvwxyz123456...",
      },
      TS018f93a3: {
        present: true,
        domain: "masar.nusuk.sa",
        path: "/",
        session: true,
        expires: null,
        valuePreview: "short-cookie",
      },
    },
  );
});

test("hasValidSessionSyncSignal requires a real session marker", () => {
  assert.equal(hasValidSessionSyncSignal(null), false);
  assert.equal(hasValidSessionSyncSignal({}), false);
  assert.equal(hasValidSessionSyncSignal({ entityId: null, jwt: null }), false);
  assert.equal(hasValidSessionSyncSignal({ entityId: "819868", jwt: null }), true);
  assert.equal(hasValidSessionSyncSignal({ entityId: "", jwt: "Bearer abc" }), true);
});

test("selectSourceMasarTab prefers active Masar app tabs over login tabs", () => {
  const selected = selectSourceMasarTab([
    { id: 1, url: "https://masar.nusuk.sa/pub/login", active: true },
    { id: 2, url: "https://masar.nusuk.sa/umrah/dashboard", active: false },
    { id: 3, url: "https://masar.nusuk.sa/umrah/mutamer/list", active: true },
  ]);

  assert.equal(selected.id, 3);
});

test("rankSourceMasarTabs keeps the preferred tab first and preserves the rest", () => {
  const ranked = rankSourceMasarTabs([
    { id: 1, url: "https://masar.nusuk.sa/pub/login", active: true },
    { id: 2, url: "https://masar.nusuk.sa/umrah/dashboard", active: false },
    { id: 3, url: "https://masar.nusuk.sa/umrah/mutamer/list", active: true },
  ]);

  assert.deepEqual(ranked.map((tab) => tab.id), [3, 1, 2]);
});

test("classifyMutamerDetailsOutcome detects expired session from login URL", () => {
  const outcome = classifyMutamerDetailsOutcome(
    { url: "https://masar.nusuk.sa/pub/login" },
    { title: "Masar Login", bodyText: "" },
  );

  assert.equal(outcome, "session-expired");
});

test("classifyMutamerDetailsOutcome detects missing mutamer from notfound URL", () => {
  const outcome = classifyMutamerDetailsOutcome(
    { url: "https://masar.nusuk.sa/pub/notfound" },
    { title: "Not Found", bodyText: "" },
  );

  assert.equal(outcome, "mutamer-missing");
});

test("classifyMutamerDetailsOutcome ignores generic missing text on the details route", () => {
  const outcome = classifyMutamerDetailsOutcome(
    { url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1", status: "complete" },
    { title: "Masar Nusuk | نسك مسار", bodyText: "لا يوجد نتائج في هذا القسم" },
  );

  assert.equal(outcome, "ready");
});

test("classifyMutamerDetailsOutcome detects expired session from login content on details route", () => {
  const outcome = classifyMutamerDetailsOutcome(
    { url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1", status: "complete" },
    { title: "Masar Nusuk | نسك مسار", bodyText: "تسجيل الدخول login" },
  );

  assert.equal(outcome, "session-expired");
});

test("extractMutamerDetailId parses the encoded details id from the click URL", () => {
  const detailId = extractMutamerDetailId(
    "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/pKEMnyGYXf%2B0xCsWqt6V",
  );

  assert.equal(detailId, "pKEMnyGYXf+0xCsWqt6V");
});

test("extractMasarContextFromSnapshot reads entity and contract from captured storage", () => {
  const context = extractMasarContextFromSnapshot({
    sessionEntries: [
      ["pms-ac_En_Id", "819868"],
      ["pms-ac_En_Type_Id", "58"],
      ["pms-tk_session", "jwt-token"],
    ],
    localCurrentContract: "{\"contractId\":222452}",
  });

  assert.deepEqual(context, {
    entityId: "819868",
    entityTypeId: "58",
    authToken: "jwt-token",
    contractId: "222452",
    hasContract: true,
  });
});

test("markRecordMissing patches the backend record with missing status", async () => {
  const requests = [];
  global.API_BASE_URL = "https://passport-api.mr3od.dev";
  global.chrome = {
    storage: {
      local: {
        get: (_keys, callback) => callback({ api_token: "token" }),
        set: (_values, callback) => callback?.(),
      },
    },
  };
  global.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    if (url.endsWith("/records/42")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          upload_id: 42,
          masar_detail_id: "detail-123",
          submission_entity_id: "819868",
          submission_entity_type_id: "58",
          submission_entity_name: "Agency Entity",
          submission_contract_id: "222452",
          submission_contract_name: "Contract A",
        }),
      };
    }
    return { ok: true, status: 200 };
  };

  const result = await markRecordMissing(42);

  assert.equal(result, true);
  const patchRequest = requests.find((entry) => entry.url.endsWith("/records/42/masar-status"));
  assert.equal(Boolean(patchRequest), true);
  assert.equal(patchRequest.options.method, "PATCH");
  assert.equal(
    patchRequest.options.body,
    JSON.stringify({
      status: "missing",
      masar_detail_id: "detail-123",
      failure_reason_code: null,
      failure_reason_text: null,
      submission_entity_id: "819868",
      submission_entity_type_id: "58",
      submission_entity_name: "Agency Entity",
      submission_contract_id: "222452",
      submission_contract_name: "Contract A",
      submission_contract_name_ar: null,
      submission_contract_name_en: null,
      submission_contract_number: null,
      submission_contract_status: null,
      submission_uo_subscription_status_id: null,
    }),
  );
  delete global.API_BASE_URL;
  delete global.chrome;
  delete global.fetch;
});

test("resolveMutamerDetailsOutcomeResult maps expired sessions to inaccessible errors", async () => {
  assert.deepEqual(
    await resolveMutamerDetailsOutcomeResult("ready", null),
    { ok: true, mode: "clone" },
  );
  assert.deepEqual(
    await resolveMutamerDetailsOutcomeResult("unknown", null),
    { ok: false, errorCode: "mutamer-open-unconfirmed" },
  );
  assert.deepEqual(
    await resolveMutamerDetailsOutcomeResult("session-expired", null),
    { ok: false, errorCode: "mutamer-inaccessible" },
  );
});

test("handleMessage accepts popup log events", async () => {
  const response = await handleMessage({
    type: "POPUP_LOG",
    scope: "details experiment",
    args: ["hello", { step: "capture" }],
  });

  assert.deepEqual(response, { ok: true });
});

test("handleMessage opens Masar entry when no source tab exists for details experiment", async () => {
  let createdUrl = null;
  global.chrome = {
    tabs: {
      query: async () => [],
      create: async ({ url, active }) => {
        createdUrl = { url, active };
        return { id: 10, windowId: 5 };
      },
    },
    storage: {
      local: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async () => ({
    status: 200,
    json: async () => ({ Status: true, data: { id: 7 } }),
  });

  const response = await handleMessage({
    type: "OPEN_MUTAMER_DETAILS_EXPERIMENT",
    clickUrl: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/7",
  });

  assert.deepEqual(createdUrl, {
    url: "https://masar.nusuk.sa/pub/login",
    active: true,
  });
  assert.deepEqual(response, { ok: true, mode: "entry" });
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage clears stale contract snapshot when contract refresh returns no contracts", async () => {
  const writes = [];
  let requestHeaders = null;
  global.chrome = {
    storage: {
      local: {
        get: (_keys, callback) => callback({
          masar_entity_id: "819868",
          masar_entity_type_id: "58",
          masar_auth_token: "Bearer token",
          masar_contract_id: "222452",
          masar_contract_name_en: "Contract A",
          masar_contract_name_ar: "العقد أ",
          masar_contract_number: "12",
          masar_contract_end_date: "2026-12-31T00:00:00",
          masar_contract_status_name: "Active",
          masar_contract_state: "active",
        }),
        set: (values, callback) => {
          writes.push(values);
          callback?.();
        },
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async (_url, init) => {
    requestHeaders = init?.headers || null;
    return {
      ok: true,
      status: 200,
      json: async () => ({ response: { data: { contracts: [] } } }),
    };
  };

  const response = await handleMessage({ type: "FETCH_CONTRACTS" });

  assert.deepEqual(response, { ok: true, contracts: [] });
  assert.equal(requestHeaders.contractid, "");
  assert.equal(requestHeaders.activeentityid, "819868");
  assert.deepEqual(writes, [{
    masar_contract_id: "",
    masar_contract_name_en: "",
    masar_contract_name_ar: "",
    masar_contract_number: "",
    masar_contract_end_date: "",
    masar_contract_status_name: "",
    masar_contract_state: "unknown",
  }]);

  delete global.chrome;
  delete global.fetch;
});

test("handleMessage fetches a paginated record page from the slim records endpoint", async () => {
  let requestedUrl = null;
  global.API_BASE_URL = "https://passport-api.mr3od.dev";
  global.chrome = {
    storage: {
      local: {
        get: (_keys, callback) => callback({ api_token: "token" }),
        set: (_values, callback) => callback?.(),
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async (url) => {
    requestedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [{ upload_id: 10, upload_status: "processed", review_status: "auto", masar_status: null }],
        limit: 50,
        offset: 0,
        total: 240,
        has_more: true,
      }),
    };
  };

  const response = await handleMessage({
    type: "FETCH_RECORD_PAGE",
    section: "pending",
    limit: 50,
    offset: 0,
  });

  assert.equal(requestedUrl.endsWith("/records?section=pending&limit=50&offset=0"), true);
  assert.deepEqual(response, {
    ok: true,
    data: {
      items: [{ upload_id: 10, upload_status: "processed", review_status: "auto", masar_status: null }],
      limit: 50,
      offset: 0,
      total: 240,
      has_more: true,
    },
  });
  delete global.API_BASE_URL;
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage maps record page auth failures to backend-auth", async () => {
  global.API_BASE_URL = "https://passport-api.mr3od.dev";
  global.chrome = {
    storage: {
      local: {
        get: (_keys, callback) => callback({ api_token: "token" }),
        set: (_values, callback) => callback?.(),
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async () => ({
    ok: false,
    status: 401,
  });

  const response = await handleMessage({
    type: "FETCH_RECORD_PAGE",
    section: "pending",
    limit: 50,
    offset: 0,
  });

  assert.deepEqual(response, {
    ok: false,
    status: 401,
    failureKind: "backend-auth",
  });
  delete global.API_BASE_URL;
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage fetches server counts for record sections", async () => {
  global.API_BASE_URL = "https://passport-api.mr3od.dev";
  global.chrome = {
    storage: {
      local: {
        get: (_keys, callback) => callback({ api_token: "token" }),
        set: (_values, callback) => callback?.(),
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ pending: 1, submitted: 2, failed: 3 }),
  });

  const response = await handleMessage({ type: "FETCH_RECORD_COUNTS" });

  assert.deepEqual(response, {
    ok: true,
    data: { pending: 1, submitted: 2, failed: 3 },
  });
  delete global.API_BASE_URL;
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage fetches submit-eligible ids only", async () => {
  let requestedUrl = null;
  global.API_BASE_URL = "https://passport-api.mr3od.dev";
  global.chrome = {
    storage: {
      local: {
        get: (_keys, callback) => callback({ api_token: "token" }),
        set: (_values, callback) => callback?.(),
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async (url) => {
    requestedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [{ upload_id: 10, upload_status: "processed", review_status: "auto", masar_status: null }],
        limit: 100,
        offset: 0,
        total: 1,
        has_more: false,
      }),
    };
  };

  const response = await handleMessage({
    type: "FETCH_SUBMIT_ELIGIBLE_IDS",
    section: "pending",
    limit: 100,
    offset: 0,
  });

  assert.equal(requestedUrl.endsWith("/records/ids?section=pending&limit=100&offset=0"), true);
  assert.deepEqual(response, {
    ok: true,
    data: {
      items: [{ upload_id: 10, upload_status: "processed", review_status: "auto", masar_status: null }],
      limit: 100,
      offset: 0,
      total: 1,
      has_more: false,
    },
  });
  delete global.API_BASE_URL;
  delete global.chrome;
  delete global.fetch;
});


test("handleMessage preserves the cloned tab when the details route is not reached before timeout", async () => {
  const operations = [];
  let snapshotCalls = 0;
  global.chrome = {
    tabs: {
      query: async () => [
        { id: 21, windowId: 2, url: "https://masar.nusuk.sa/pub/login", active: false },
        { id: 22, windowId: 2, url: "https://masar.nusuk.sa/umrah/dashboard", active: true },
      ],
      create: async ({ url, active }) => {
        operations.push(["create", { url, active }]);
        return { id: 30, windowId: 7, pendingUrl: url, status: "loading" };
      },
      update: async (tabId, payload) => {
        operations.push(["update", { tabId, payload }]);
        return { id: tabId, windowId: tabId === 22 ? 2 : 7 };
      },
      get: async (tabId) => {
        if (tabId === 30) {
          snapshotCalls += 1;
          return {
            id: 30,
            windowId: 7,
            url: "https://masar.nusuk.sa/pub/login",
            pendingUrl: undefined,
            title: "Masar Login",
            status: "complete",
          };
        }
        return { id: tabId, windowId: 2, url: "https://masar.nusuk.sa/umrah/dashboard", status: "complete" };
      },
    },
    windows: {
      update: async (windowId, payload) => {
        operations.push(["window", { windowId, payload }]);
      },
    },
    scripting: {
      executeScript: async ({ target, args }) => {
        if (!args) {
          return [{
            result: {
              sessionEntries: [["pms-tk_session", "jwt"]],
              localCurrentContract: "{\"contractId\":\"55\"}",
            },
          }];
        }
        return [{ result: true }];
      },
    },
    storage: {
      local: {
        get: (_keys, callback) => callback({}),
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async () => ({
    status: 200,
    json: async () => ({ Status: true, data: { id: 7 } }),
  });

  const response = await handleMessage({
    type: "OPEN_MUTAMER_DETAILS_EXPERIMENT",
    clickUrl: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/7",
  });

  assert.equal(snapshotCalls > 1, true);
  assert.deepEqual(operations, [
    ["create", { url: "https://masar.nusuk.sa/pub/login", active: false }],
    ["update", { tabId: 30, payload: { url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/7", active: false } }],
    ["update", { tabId: 30, payload: { active: true } }],
    ["window", { windowId: 7, payload: { focused: true } }],
  ]);
  assert.deepEqual(response, { ok: true, mode: "clone-pending" });
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage falls back to reuse when the captured snapshot has no session auth", async () => {
  const operations = [];
  global.chrome = {
    tabs: {
      query: async () => [
        { id: 22, windowId: 2, url: "https://masar.nusuk.sa/umrah/dashboard", active: true },
      ],
      create: async ({ url, active }) => {
        operations.push(["create", { url, active }]);
        return { id: 30, windowId: 7, pendingUrl: url, status: "loading" };
      },
      update: async (tabId, payload) => {
        operations.push(["update", { tabId, payload }]);
        return { id: tabId, windowId: 2, ...payload };
      },
      get: async (tabId) => ({
        id: tabId,
        windowId: 2,
        url: "https://masar.nusuk.sa/umrah/dashboard",
        status: "complete",
      }),
    },
    windows: {
      update: async (windowId, payload) => {
        operations.push(["window", { windowId, payload }]);
      },
    },
    scripting: {
      executeScript: async ({ args }) => {
        if (args) {
          return [{ result: true }];
        }
        return [{
          result: {
            sessionEntries: [],
            localCurrentContract: "{\"contractId\":111111}",
          },
        }];
      },
    },
    storage: {
      local: {
        get: (_keys, callback) => callback({}),
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async () => ({
    status: 200,
    json: async () => ({ Status: true, data: { id: 7 } }),
  });

  const response = await handleMessage({
    type: "OPEN_MUTAMER_DETAILS_EXPERIMENT",
    clickUrl: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/7",
  });

  assert.deepEqual(response, { ok: true, mode: "reuse" });
  assert.deepEqual(operations, [
    ["update", { tabId: 22, payload: { url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/7", active: true } }],
    ["window", { windowId: 2, payload: { focused: true } }],
  ]);
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage falls back to the record detail fetch when row details context is incomplete", async () => {
  let recordFetches = 0;
  global.API_BASE_URL = "https://passport-api.mr3od.dev";
  global.chrome = {
    tabs: {
      query: async () => [
        { id: 12, windowId: 2, url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-list", active: true },
      ],
      create: async () => ({ id: 30, windowId: 7, pendingUrl: "https://masar.nusuk.sa/pub/login", status: "loading" }),
      update: async (tabId, payload) => ({ id: tabId, windowId: tabId === 12 ? 2 : 7, ...payload }),
      get: async () => ({
        id: 30,
        windowId: 7,
        url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1",
        pendingUrl: undefined,
        title: "Masar Nusuk | نسك مسار",
        status: "complete",
      }),
      remove: async () => {},
    },
    windows: {
      update: async () => {},
    },
    scripting: {
      executeScript: async ({ target, args }) => {
        if (args) {
          return [{ result: true }];
        }
        if (target.tabId === 12) {
          return [{
            result: {
              sessionEntries: [
                ["pms-ac_En_Id", "819455"],
                ["pms-ac_En_Type_Id", "58"],
                ["pms-tk_session", "jwt-b"],
              ],
              localCurrentContract: "{\"contractId\":111111}",
            },
          }];
        }
        return [{ result: { href: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1", title: "Masar Nusuk | نسك مسار", bodyText: "passport number group details" } }];
      },
    },
    storage: {
      local: {
        get: (_keys, callback) => callback({}),
        set: (_values, callback) => callback?.(),
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async (url) => {
    if (url.endsWith("/records/77")) {
      recordFetches += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          upload_id: 77,
          submission_entity_id: "819868",
          submission_entity_type_id: "58",
          submission_contract_id: "222452",
          submission_contract_name: "Contract A",
          submission_contract_name_ar: "العقد أ",
          submission_contract_name_en: "Contract A",
          submission_contract_number: "0025",
          submission_contract_status: true,
          submission_uo_subscription_status_id: 1,
        }),
      };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };

  const response = await handleMessage({
    type: "OPEN_MUTAMER_DETAILS_EXPERIMENT",
    clickUrl: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1",
    uploadId: 77,
    detailsContext: {
      submission_entity_id: null,
      submission_entity_type_id: null,
      submission_contract_id: null,
      submission_contract_name: null,
      submission_contract_name_ar: null,
      submission_contract_name_en: null,
      submission_contract_number: null,
      submission_contract_status: null,
      submission_uo_subscription_status_id: null,
    },
  });

  assert.equal(recordFetches, 1);
  assert.deepEqual(response, { ok: true, mode: "clone" });
  delete global.API_BASE_URL;
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage rejects batch resume when no persisted batch exists", async () => {
  global.chrome = {
    storage: {
      local: {
        get: (_keys, callback) => callback({}),
      },
      session: {
        get: (_keys, callback) => callback({
          submission_batch: null,
          active_submit_id: null,
        }),
      },
    },
  };

  const response = await handleMessage({
    type: "SUBMIT_BATCH",
    uploadIds: [],
  });

  assert.deepEqual(response, { ok: false, errorCode: "submission-batch-missing" });
  delete global.chrome;
});

test("handleMessage returns missing-record failure after cloned tab lands on notfound", async () => {
  const operations = [];
  let queriedTabs = false;
  let preflightCalled = false;
  let patchRequest = null;
  global.API_BASE_URL = "https://passport-api.mr3od.dev";
  global.chrome = {
    tabs: {
      query: async () => {
        queriedTabs = true;
        return [{ id: 15, windowId: 3, url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-list", active: true }];
      },
      create: async ({ url, active }) => {
        operations.push(["create", { url, active }]);
        return { id: 30, windowId: 7, pendingUrl: url, status: "loading" };
      },
      update: async (tabId, payload) => {
        operations.push(["update", { tabId, payload }]);
        return { id: tabId, windowId: 7, ...payload };
      },
      get: async () => ({
        id: 30,
        windowId: 7,
        url: "https://masar.nusuk.sa/pub/notfound",
        pendingUrl: undefined,
        title: "Not Found",
        status: "complete",
      }),
      remove: async () => {},
    },
    windows: {
      update: async () => {},
    },
    scripting: {
      executeScript: async ({ args }) => {
        if (Array.isArray(args) && typeof args[0] === "string") {
          preflightCalled = true;
          return [{ result: null }];
        }
        if (args) {
          return [{ result: true }];
        }
        return [
          {
            result: {
              sessionEntries: [
                ["pms-ac_En_Id", "819868"],
                ["pms-ac_En_Type_Id", "58"],
                ["pms-tk_session", "Bearer token"],
              ],
              localCurrentContract: "{\"contractId\":222452}",
            },
          },
        ];
      },
    },
    storage: {
      local: {
        get: (_keys, callback) => callback({
          masar_entity_id: "819868",
          masar_entity_type_id: "58",
          masar_contract_id: "222452",
          masar_auth_token: "Bearer token",
        }),
        set: (_values, callback) => callback?.(),
      },
    },
  };
  global.fetch = async (url, options = {}) => {
    if (url.endsWith("/records/77")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          upload_id: 77,
          masar_detail_id: "detail-123",
          submission_entity_id: "819868",
          submission_entity_type_id: "58",
          submission_entity_name: "Agency Entity",
          submission_contract_id: "222452",
          submission_contract_name: "Contract A",
        }),
      };
    }
    patchRequest = { url, options };
    return {
      ok: true,
      status: 200,
      json: async () => ({}),
    };
  };

  const response = await handleMessage({
    type: "OPEN_MUTAMER_DETAILS_EXPERIMENT",
    clickUrl: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/pKEMnyGYXf%2B0xCsWqt6V",
    uploadId: 77,
  });

  assert.equal(queriedTabs, true);
  assert.equal(preflightCalled, false);
  assert.deepEqual(response, { ok: false, errorCode: "mutamer-missing" });
  assert.equal(patchRequest.url.endsWith("/records/77/masar-status"), true);
  assert.deepEqual(operations[0], ["create", { url: "https://masar.nusuk.sa/pub/login", active: false }]);
  assert.equal(
    patchRequest.options.body,
    JSON.stringify({
      status: "missing",
      masar_detail_id: "detail-123",
      failure_reason_code: null,
      failure_reason_text: null,
      submission_entity_id: "819868",
      submission_entity_type_id: "58",
      submission_entity_name: "Agency Entity",
      submission_contract_id: "222452",
      submission_contract_name: "Contract A",
      submission_contract_name_ar: null,
      submission_contract_name_en: null,
      submission_contract_number: null,
      submission_contract_status: null,
      submission_uo_subscription_status_id: null,
    }),
  );
  delete global.API_BASE_URL;
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage waits for rendered details content before activating the cloned tab", async () => {
  const operations = [];
  let probeCalls = 0;
  global.chrome = {
    tabs: {
      query: async () => [
        { id: 12, windowId: 2, url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-list", active: true },
      ],
      create: async ({ url, active }) => {
        operations.push(["create", { url, active }]);
        return { id: 30, windowId: 7, pendingUrl: url, status: "loading", active };
      },
      update: async (tabId, payload) => {
        operations.push(["update", { tabId, payload }]);
        return { id: tabId, windowId: tabId === 12 ? 2 : 7, ...payload };
      },
      get: async () => ({
        id: 30,
        windowId: 7,
        url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1",
        pendingUrl: undefined,
        title: "Masar Nusuk | نسك مسار",
        status: "complete",
      }),
    },
    windows: {
      update: async (windowId, payload) => {
        operations.push(["window", { windowId, payload }]);
      },
    },
    scripting: {
      executeScript: async ({ target, args }) => {
        if (args) {
          return [{ result: true }];
        }
        if (target.tabId === 12) {
          return [{
            result: {
              sessionEntries: [
                ["pms-ac_En_Id", "819868"],
                ["pms-ac_En_Type_Id", "58"],
                ["pms-tk_session", "jwt-b"],
              ],
              localCurrentContract: "{\"contractId\":222452}",
            },
          }];
        }
        probeCalls += 1;
        if (probeCalls === 1) {
          return [{ result: { href: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1", title: "Masar Nusuk | نسك مسار", bodyText: "login تسجيل الدخول" } }];
        }
        return [{ result: { href: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1", title: "Masar Nusuk | نسك مسار", bodyText: "passport number group details" } }];
      },
    },
    storage: {
      local: {
        get: (_keys, callback) => callback({}),
      },
      session: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });

  await handleMessage({
    type: "OPEN_MUTAMER_DETAILS_EXPERIMENT",
    clickUrl: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1",
  });

  const activationIndex = operations.findIndex(
    ([type, payload]) => type === "update" && payload.tabId === 30 && payload.payload.active === true,
  );
  const navigateIndex = operations.findIndex(
    ([type, payload]) => type === "update" && payload.tabId === 30 && payload.payload.url,
  );
  assert.equal(probeCalls >= 2, true);
  assert.equal(activationIndex > navigateIndex, true);
  delete global.chrome;
  delete global.fetch;
});

test("handleMessage returns inaccessible when cloned tab stays on login content", async () => {
  let preflightCalled = false;
  let inspectCalls = 0;
  global.chrome = {
    tabs: {
      query: async () => [
        { id: 12, windowId: 2, url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-list", active: true },
      ],
      create: async () => ({ id: 30, windowId: 7, pendingUrl: "https://masar.nusuk.sa/pub/login", status: "loading" }),
      update: async () => ({ id: 30, windowId: 7 }),
      get: async () => ({
        id: 30,
        windowId: 7,
        url: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1",
        pendingUrl: undefined,
        title: "Masar Nusuk | نسك مسار",
        status: "complete",
      }),
      remove: async () => {},
    },
    windows: {
      update: async () => {},
    },
    scripting: {
      executeScript: async ({ target, args }) => {
        if (Array.isArray(args) && typeof args[0] === "string") {
          preflightCalled = true;
          return [{ result: null }];
        }
        if (args) {
          return [{ result: true }];
        }
        if (target.tabId === 12) {
          return [
            {
              result: {
                sessionEntries: [
                  ["pms-ac_En_Id", "819868"],
                  ["pms-ac_En_Type_Id", "58"],
                  ["pms-tk_session", "jwt-b"],
                ],
                localCurrentContract: "{\"contractId\":222452}",
              },
            },
          ];
        }
        inspectCalls += 1;
        return [{ result: { href: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1", title: "Masar Nusuk | نسك مسار", bodyText: "login تسجيل الدخول" } }];
      },
    },
    storage: {
      local: {
        get: (_keys, callback) => callback({}),
      },
    },
  };
  global.fetch = async () => {
    throw new Error("unexpected fetch");
  };

  const response = await handleMessage({
    type: "OPEN_MUTAMER_DETAILS_EXPERIMENT",
    clickUrl: "https://masar.nusuk.sa/umrah/mutamer/mutamer-details/detail-1",
  });

  assert.equal(preflightCalled, false);
  assert.equal(inspectCalls >= 3, true);
  assert.deepEqual(response, { ok: false, errorCode: "mutamer-inaccessible" });
  delete global.chrome;
  delete global.fetch;
});
