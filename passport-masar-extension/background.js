if (typeof importScripts === "function") {
  importScripts("config.js");
  importScripts("strings.js");
  importScripts("badge.js");
  importScripts("notifications.js");
  importScripts("context-change.js");
}

const S = globalThis.S || (typeof require === "function" ? require("./strings.js") : undefined);
const Badge = globalThis.MasarBadge || (typeof require === "function" ? require("./badge.js") : undefined);
const Notifications =
  globalThis.MasarNotifications || (typeof require === "function" ? require("./notifications.js") : undefined);
const ContextChange =
  globalThis.MasarContextChange || (typeof require === "function" ? require("./context-change.js") : undefined);

// ─── Header capture ───────────────────────────────────────────────────────────
// Passively observe every outgoing request to masar and persist entity headers.
const debouncedContextChecker =
  ContextChange?.createDebouncedContextChecker?.((context) => {
    void handleStableContextChange(context);
  }, 1500) || null;

if (typeof chrome !== "undefined" && chrome.webRequest?.onSendHeaders) {
  chrome.webRequest.onSendHeaders.addListener((details) => {
    const h = {};
    details.requestHeaders.forEach((r) => { h[r.name.toLowerCase()] = r.value; });
    if (h["activeentityid"]) {
      const context = {
        entity_id: h["activeentityid"],
        entity_type_id: h["activeentitytypeid"] || null,
        contract_id: h["contractid"] || null,
        auth_token: null,
        user_name: null,
      };
      if (h["authorization"]) {
        const authVal = h["authorization"].replace(/^"|"$/g, "");
        context.auth_token = authVal;
        try {
          const payload = JSON.parse(atob(authVal.replace(/^Bearer\s+/i, "").split(".")[1]));
          if (payload.name) context.user_name = payload.name;
        } catch (_) {}
      }
      void captureObservedContext(context);
    }
  },
  { urls: ["https://masar.nusuk.sa/*", "https://*.nusuk.sa/*"] },
  ["requestHeaders", "extraHeaders"]);
}

// ─── Badge ────────────────────────────────────────────────────────────────────

function updateBadge(records) {
  return updateBadgeState({ failedCount: countFailedRecords(records) });
}

function countFailedRecords(records) {
  return (Array.isArray(records) ? records : []).filter(
    (record) => record.upload_status === "failed" || record.masar_status === "failed",
  ).length;
}

function taggedError(failureKind, message) {
  const error = new Error(message);
  if (failureKind) {
    error.failureKind = failureKind;
  }
  return error;
}

// ─── Submission serializer ────────────────────────────────────────────────────
// Only one SUBMIT_RECORD runs at a time. Concurrent calls queue behind the
// current one — prevents parallel Attachment/Upload 429s from Cloudflare and
// ensures no orphaned partial mutamers are left in Masar.
let _submitChain = Promise.resolve();
function serialiseSubmit(fn) {
  const next = _submitChain.then(() => fn());
  _submitChain = next.catch(() => {}); // keep chain alive on failure
  return next;
}

// ─── Logging ──────────────────────────────────────────────────────────────────

function log(...args) {
  console.log("[masar-ext]", ...args);
}
function logError(...args) {
  console.error("[masar-ext]", ...args);
}

function localGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function localSet(values) {
  return new Promise((resolve) => chrome.storage.local.set(values, resolve));
}

function localRemove(keys) {
  return new Promise((resolve) => chrome.storage.local.remove(keys, resolve));
}

function sessionGet(keys) {
  return new Promise((resolve) => chrome.storage.session.get(keys, resolve));
}

function sessionSet(values) {
  return new Promise((resolve) => chrome.storage.session.set(values, resolve));
}

// ─── Masar API helpers ────────────────────────────────────────────────────────

async function getMasarEntityHeaders() {
  return new Promise((resolve) => {
    chrome.storage.local.get(
      ["masar_entity_id", "masar_entity_type_id", "masar_contract_id", "masar_auth_token"],
      (items) => resolve(items)
    );
  });
}

// Build custom entity headers — do NOT include Cookie.
// The browser sends cookies automatically via credentials:'include' for
// requests that match host_permissions. Setting Cookie manually is a
// forbidden-header no-op in the Fetch API.
async function buildMasarHeaders() {
  const stored = await getMasarEntityHeaders();
  const headers = {
    activeentityid: stored.masar_entity_id || "",
    activeentitytypeid: stored.masar_entity_type_id || "",
    contractid: stored.masar_contract_id || "",
    "entity-id": stored.masar_entity_id || "",
    "Content-Type": "application/json",
    accept: "application/json, text/plain, */*",
    "accept-language": "en",
  };
  if (stored.masar_auth_token) {
    headers["Authorization"] = stored.masar_auth_token;
  }
  return headers;
}

// ─── Masar fetch helpers ──────────────────────────────────────────────────────
// Direct fetch from service worker — same approach that was working before.

async function masarFetch(url, options = {}) {
  const headers = await buildMasarHeaders();
  const { headers: extra, body, method, ...rest } = options;
  const mergedHeaders = { ...headers, ...(extra || {}) };
  log(`masarFetch — ${method || "GET"} ${url}`);
  const res = await fetch(url, {
    ...rest,
    method: method || "GET",
    credentials: "include",
    headers: mergedHeaders,
    body: body !== undefined ? body : undefined,
  });
  log(`masarFetch ← ${res.status}`);
  return res;
}

// Multipart — builds a real FormData in the service worker and sends directly.
async function masarFetchMultipart(url, formData) {
  const stored = await getMasarEntityHeaders();
  log("masarFetchMultipart —", url, "entityId:", stored.masar_entity_id, "contractId:", stored.masar_contract_id, "hasAuth:", !!stored.masar_auth_token);
  const headers = {
    activeentityid: stored.masar_entity_id || "",
    activeentitytypeid: stored.masar_entity_type_id || "",
    contractid: stored.masar_contract_id || "",
    "entity-id": stored.masar_entity_id || "",
    accept: "application/json, text/plain, */*",
    "accept-language": "en",
  };
  if (stored.masar_auth_token) headers["Authorization"] = stored.masar_auth_token;
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers,
    body: formData,
  });
  log(`masarFetchMultipart ← ${res.status}`);
  return res;
}

// Read all session values directly from the open masar tab's storage.
// sessionStorage: pms-ac_En_Id (entityId), pms-ac_En_Type_Id (entityTypeId), pms-tk_session (JWT)
// localStorage:   currentContract.contractId
async function syncSessionFromMasar() {
  try {
    const tabs = await chrome.tabs.query({ url: "https://masar.nusuk.sa/*" });
    if (tabs.length === 0) {
      log("syncSessionFromMasar — no open masar tab");
      return;
    }
    const results = await chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      func: () => {
        const contract = (() => {
          try { return JSON.parse(localStorage.getItem("currentContract") || "null"); } catch { return null; }
        })();
        // User name is decoded from the webRequest-captured JWT — no need to re-read here.
        return {
          entityId:           sessionStorage.getItem("pms-ac_En_Id"),
          entityTypeId:       sessionStorage.getItem("pms-ac_En_Type_Id"),
          jwt:                sessionStorage.getItem("pms-tk_session"),
          contractId:         contract?.contractId ? String(contract.contractId) : null,
          contractNumber:     contract?.contractNumber ? String(contract.contractNumber) : null,
          contractNameEn:     contract?.companyNameEn || null,
          contractNameAr:     contract?.companyNameAr || null,
          contractEndDate:    contract?.contractEndDate || null,
          contractStatusName: contract?.contractStatus?.name || null,
        };
      },
    });
    const s = results?.[0]?.result;
    if (!s) return;

    // Determine contract state.
    // contractEndDate is midnight that starts the end day; treat same-day as "expires today".
    let contractState = "unknown"; // "active" | "expires-today" | "expired" | "unknown"
    if (s.contractEndDate) {
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const end = new Date(s.contractEndDate);
      const endDayStart = new Date(end.getFullYear(), end.getMonth(), end.getDate());
      if (todayStart > endDayStart) contractState = "expired";
      else if (todayStart.getTime() === endDayStart.getTime()) contractState = "expires-today";
      else contractState = "active";
    }

    log("syncSessionFromMasar —", {
      entityId: s.entityId, contractId: s.contractId,
      contractNameEn: s.contractNameEn, contractState,
      userNameEn: s.userNameEn, hasJwt: !!s.jwt,
    });

    const stored = await localGet(["masar_contract_manual_override"]);
    const update = {};
    if (s.entityId)           update.masar_entity_id            = s.entityId;
    if (s.entityTypeId)       update.masar_entity_type_id       = s.entityTypeId;
    if (!stored.masar_contract_manual_override) {
      if (s.contractId)         update.masar_contract_id          = s.contractId;
      if (s.contractNumber)     update.masar_contract_number      = s.contractNumber;
      if (s.contractNameEn)     update.masar_contract_name_en     = s.contractNameEn;
      if (s.contractNameAr)     update.masar_contract_name_ar     = s.contractNameAr;
      if (s.contractEndDate)    update.masar_contract_end_date    = s.contractEndDate;
      if (s.contractStatusName) update.masar_contract_status_name = s.contractStatusName;
      update.masar_contract_state = contractState;
    }
    // masar_user_name is decoded from JWT in the webRequest listener — not sourced here.
    await captureObservedContext({
      entity_id: s.entityId,
      entity_type_id: s.entityTypeId,
      contract_id: s.contractId,
      auth_token: null,
      user_name: null,
    });
    if (Object.keys(update).length) {
      chrome.storage.local.set(update);
    }
  } catch (err) {
    // "Frame with ID 0 is showing error page" — masar tab is closed or on an error page.
    // Non-fatal: webRequest-captured values remain in storage and are used instead.
    if (err.message?.includes("error page") || err.message?.includes("Cannot access")) {
      log("syncSessionFromMasar — tab unavailable:", err.message);
    } else {
      logError("syncSessionFromMasar — error:", err.message);
    }
  }
}

// Sync session data from the open masar tab into chrome.storage.local.
// Returns { ok: true } always — errors are non-fatal.
async function syncSession() {
  try {
    await syncSessionFromMasar();
    chrome.storage.local.set({ masar_last_synced: Date.now(), session_expired: false });
    const stored = await getMasarEntityHeaders();
    log("syncSession — entityId:", stored.masar_entity_id, "contractId:", stored.masar_contract_id, "hasAuthToken:", !!stored.masar_auth_token);
    await updateBadgeState();
    return { ok: true };
  } catch (err) {
    logError("syncSession — error:", err.message);
    return { ok: true }; // non-fatal
  }
}

async function captureObservedContext(context) {
  const stored = await localGet([
    "masar_entity_id",
    "masar_contract_id",
    "masar_contract_manual_override",
  ]);
  const hasCurrentContext = Boolean(stored.masar_entity_id || stored.masar_contract_id);
  const effectiveContractId = stored.masar_contract_manual_override ? null : context.contract_id;
  const update = {};
  if (context.entity_id) update.masar_entity_id = context.entity_id;
  if (context.entity_type_id) update.masar_entity_type_id = context.entity_type_id;
  if (effectiveContractId) update.masar_contract_id = effectiveContractId;
  if (context.auth_token) update.masar_auth_token = context.auth_token;
  if (context.user_name) update.masar_user_name = context.user_name;
  if (!hasCurrentContext) {
    await localSet(update);
    return;
  }
  if (debouncedContextChecker) {
    debouncedContextChecker({
      ...context,
      contract_id: effectiveContractId,
    });
  }
}

async function handleStableContextChange(context) {
  const change = await ContextChange.detectContextChange(context);
  if (!change) {
    const update = {};
    if (context.entity_id) update.masar_entity_id = context.entity_id;
    if (context.entity_type_id) update.masar_entity_type_id = context.entity_type_id;
    if (context.contract_id) update.masar_contract_id = context.contract_id;
    if (context.auth_token) update.masar_auth_token = context.auth_token;
    if (context.user_name) update.masar_user_name = context.user_name;
    if (Object.keys(update).length) {
      await localSet(update);
    }
    return;
  }
  await updateBadgeState();
  await Notifications.notify(
    Notifications.NOTIFICATION_TYPES.CONTEXT_CHANGE,
    change.reason === "entity_changed" ? S.CTX_CHANGED_ENTITY : S.CTX_CHANGED_CONTRACT,
  );
}

async function fetchGroups() {
  log("fetchGroups — calling GetGroupList");
  const res = await masarFetch(
    "https://masar.nusuk.sa/umrah/groups_apis/api/Groups/GetGroupList",
    {
      method: "POST",
      body: JSON.stringify({
        limit: 50,
        offset: 0,
        filterList: [],
        sortColumn: null,
        sortCriteria: [],
        noCount: false,
      }),
    }
  );
  log("fetchGroups — status:", res.status);
  if (!res.ok) throw taggedError(res.status === 401 ? "masar-auth" : null, `groups ${res.status}`);
  const json = await res.json();
  log("fetchGroups — raw response:", JSON.stringify(json).slice(0, 500));
  return json;
}

// ─── Passport-API helpers ─────────────────────────────────────────────────────

async function getApiToken() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["api_token"], (items) => resolve(items.api_token || null));
  });
}

async function apiFetch(path, options = {}) {
  const token = await getApiToken();
  log(`apiFetch — ${options.method || "GET"} ${API_BASE_URL}${path} token:`, token ? token.slice(0, 20) + "..." : "MISSING");
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  log(`apiFetch — response status:`, res.status);
  return res;
}

async function fetchAllRecords() {
  const response = await apiFetch("/records?limit=200");
  if (!response.ok) {
    if (response.status === 401) {
      await localSet({ session_expired: true });
      await updateBadgeState({ failedCount: 0 });
    }
    return {
      ok: false,
      status: response.status,
      failureKind: response.status === 401 ? "backend-auth" : null,
    };
  }
  await localSet({ session_expired: false });
  const data = await response.json();
  await updateBadgeState({
    failedCount: countFailedRecords(data),
  });
  return { ok: true, data: Array.isArray(data) ? data : [] };
}

function shouldSubmitRecord(record) {
  return record?.upload_status === "processed" && (!record?.masar_status || record.masar_status === "failed");
}

async function updateBadgeState({ failedCount = null } = {}) {
  const localState = await localGet(["session_expired"]);
  const contextChangePending = await ContextChange.hasContextChangePending();
  const badgeState = Badge.computeBadgeState({
    sessionExpired: Boolean(localState.session_expired),
    contextChangePending,
    failedCount: failedCount ?? 0,
  });
  await Badge.applyBadge(badgeState);
}

async function fetchContracts() {
  const response = await masarFetch(
    "https://masar.nusuk.sa/umrah/contracts_apis/api/ExternalAgent/GetContractList",
    {
      method: "POST",
      body: JSON.stringify({
        umrahCompanyName: null,
        contractStartDate: null,
        contractEndDate: null,
      }),
    },
  );
  if (!response.ok) {
    throw taggedError(response.status === 401 ? "masar-auth" : null, `contracts ${response.status}`);
  }
  const payload = await response.json();
  return payload?.response?.data?.contracts || [];
}

async function patchRecordStatus(uploadId, body) {
  const response = await apiFetch(`/records/${uploadId}/masar-status`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw taggedError(response.status === 401 ? "backend-auth" : null, S.ERR_PATCH_FAILED(response.status));
  }
}

async function getRecordById(uploadId) {
  const records = await fetchAllRecords();
  if (!records.ok) {
    throw taggedError(records.status === 401 ? "backend-auth" : null, S.ERR_UNEXPECTED);
  }
  return records.data.find((record) => record.upload_id === uploadId) || null;
}

async function clearSubmissionBatch() {
  await sessionSet({
    submission_batch: [],
    active_submit_id: null,
    submission_state: ContextChange.SUBMISSION_STATES.IDLE,
  });
}

async function removeFromBatch(uploadId) {
  const session = await sessionGet(["submission_batch"]);
  const nextBatch = (session.submission_batch || []).filter((id) => id !== uploadId);
  await sessionSet({ submission_batch: nextBatch });
  return nextBatch;
}

// ─── Submission workflow ──────────────────────────────────────────────────────

async function fetchImageBytes(uploadId) {
  log("fetchImageBytes — upload_id:", uploadId);
  const res = await apiFetch(`/records/${uploadId}/image`);
  if (!res.ok) {
    throw taggedError(res.status === 401 ? "backend-auth" : null, S.ERR_IMAGE_FETCH(res.status));
  }
  return res.arrayBuffer();
}

// Strip characters Masar rejects from English name tokens (e.g. hyphens in "AL-AKBARI").
function sanitiseEnName(str) {
  if (!str) return null;
  const cleaned = str.replace(/[^A-Za-z\s]/g, " ").replace(/\s+/g, " ").trim();
  return cleaned || null;
}

// Strip characters Masar rejects from Arabic name/city tokens:
// - Arabic diacritics / harakat (U+064B–U+065F)
// - Tatweel / kashida (U+0640)
// - Anything outside Arabic script, Latin letters, digits, and whitespace
function sanitiseArName(str) {
  if (!str) return null;
  const cleaned = str
    .replace(/[\u0640\u064B-\u065F]/g, "")   // tatweel + harakat
    .replace(/[^\u0600-\u06FF A-Za-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned || null;
}


// passport-core emits dates as DD/MM/YYYY; Masar expects YYYY-MM-DD.
// Returns null for absent or unrecognised formats so callers can fall back to scan data.
function coreDate(str) {
  if (!str) return null;
  const m = str.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  return null;
}

function mapNameTokens(tokens, sanitise) {
  if (!Array.isArray(tokens) || tokens.length === 0) {
    return { first: null, second: null, third: null };
  }
  if (tokens.length <= 3) {
    return {
      first: sanitise(tokens[0]),
      second: sanitise(tokens[1]),
      third: sanitise(tokens[2]),
    };
  }
  return {
    first: sanitise(tokens[0]),
    second: sanitise(tokens.slice(1, -1).join(" ")),
    third: sanitise(tokens[tokens.length - 1]),
  };
}

async function submitToMasar(record) {
  const settings = await new Promise((resolve) =>
    chrome.storage.local.get(["agency_email", "agency_phone", "agency_phone_country_code"], resolve)
  );

  // passport-core OCR data — used for all text fields (better quality than ScanPassport OCR).
  // ScanPassport is still called for image uploads and numeric IDs it returns.
  const core = record.extraction_result?.data || {};
  log("submitToMasar — extraction_result fields available:", Object.keys(core).filter((k) => core[k]));

  const namesEn = mapNameTokens(core.GivenNameTokensEn, sanitiseEnName);
  const namesAr = mapNameTokens(core.GivenNameTokensAr, sanitiseArName);
  const firstEn  = namesEn.first;
  const secondEn = namesEn.second;
  const thirdEn  = namesEn.third;
  const firstAr  = namesAr.first;
  const secondAr = namesAr.second;
  const thirdAr  = namesAr.third;
  const familyEn = sanitiseEnName(core.SurnameEn);
  const familyAr = sanitiseArName(core.SurnameAr);

  // passport-core Sex: "M"/"F" → Masar gender: 1/2
  const coreGender = core.Sex === "M" ? 1 : core.Sex === "F" ? 2 : null;

  // passport-core dates are DD/MM/YYYY — convert before use.
  const coreBirthDate   = coreDate(core.DateOfBirth);
  const coreIssueDate   = coreDate(core.DateOfIssue);
  const coreExpiryDate  = coreDate(core.DateOfExpiry);

  // Marital status: agency rule is >20 → Married (2), ≤20 → Single (1).
  const martialStatusId = (() => {
    if (!coreBirthDate) return 2; // default married if birth date unknown
    const ageMs = Date.now() - new Date(coreBirthDate).getTime();
    const age = Math.floor(ageMs / (365.25 * 24 * 3600 * 1000));
    return age > 20 ? 2 : 1;
  })();

  const imageName = record.filename || "passport.jpg";
  const imageBytes = await fetchImageBytes(record.upload_id);
  const imageBlob = new Blob([imageBytes], { type: "image/jpeg" });

  // ── Step 1: ScanPassport ──────────────────────────────────────────────────
  log("submitToMasar [1/6] — ScanPassport");
  const fd1 = new FormData();
  fd1.append("passportImage", imageBlob, imageName);
  const step1Res = await masarFetchMultipart(
    "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/ScanPassport",
    fd1
  );
  log("submitToMasar [1/6] — status:", step1Res.status);
  if (!step1Res.ok) {
    const errText = await step1Res.text();
    logError("submitToMasar [1/6] — error body:", errText);
    throw taggedError(
      step1Res.status === 401 ? "masar-auth" : null,
      S.ERR_SCAN_PASSPORT(step1Res.status),
    );
  }
  const step1Json = await step1Res.json();
  // Masar returns a non-standard envelope when the scan contract is inactive:
  // { Status: false, data: null, traceError: "No Active Contract" }
  // Detect it before attempting to access response.data to avoid a silent crash.
  if (!step1Json.response || !step1Json.response.data) {
    const traceError = step1Json.traceError || step1Json.TraceError || step1Json.responseDesc || "unknown";
    logError("submitToMasar [1/6] — ScanPassport returned no data. traceError:", traceError);
    throw new Error(S.ERR_SCAN_NO_DATA);
  }
  // Response envelope: { response: { data: { passportResponse: {...}, ... } } }
  const scanData = step1Json.response.data;
  const scan = scanData.passportResponse;
  const passportImageMeta = scan.passportImage;
  const personalPictureMeta = scan.personalPicture;

  log("submitToMasar [1/6] — scanData:", JSON.stringify(scan).slice(0, 300));

  // ── Step 2: SubmitPassportInforamtionWithNationality ──────────────────────
  // Text fields from passport-core OCR; image IDs + numeric nationality IDs from ScanPassport.
  log("submitToMasar [2/6] — SubmitPassportInforamtionWithNationality");
  const step2Body = {
    id: null,
    firstName: { en: firstEn || scan.firstNameEn },
    familyName: { en: familyEn || scan.familyNameEn },
    previousNationalityId: null,
    gender: coreGender ?? scan.gender,
    passportTypeId: 1,
    birthDate: coreBirthDate || scan.birthDate,
    passportExpiryDate: coreExpiryDate || scan.passportExpiryDate,
    passportIssueDate: coreIssueDate   || scan.passportIssueDate,
    nationalityId: scan.nationalityId,   // integer ID — only available from ScanPassport
    issueCountryId: scan.countryId,      // integer ID — only available from ScanPassport
    passportNumber: core.PassportNumber || scan.passportNumber,
    // IssuingAuthority on Yemeni passports is the issuing city (MUKALLA, SEYION, etc.).
    // Prefer Arabic since Masar accepts it and agencies serve Arabic-speaking pilgrims.
    issueCityName: sanitiseArName(core.IssuingAuthorityAr) || sanitiseEnName(core.IssuingAuthorityEn) || scan.issueCity || "",
    personalPicture: null,
    passportImage: {
      id: passportImageMeta.id,
      fileName: passportImageMeta.fileName,
      fileSize: passportImageMeta.fileSize,
      fileExtension: passportImageMeta.fileExtension,
    },
    passportPictureId: passportImageMeta.id,
    personalPictureId: personalPictureMeta.id,
    signature: scan.signature,
  };
  const step2Res = await masarFetch(
    "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/SubmitPassportInforamtionWithNationality",
    { method: "POST", body: JSON.stringify(step2Body) }
  );
  log("submitToMasar [2/6] — status:", step2Res.status);
  if (!step2Res.ok) {
    throw taggedError(
      step2Res.status === 401 ? "masar-auth" : null,
      S.ERR_SUBMIT_PASSPORT(step2Res.status),
    );
  }
  const step2Json = await step2Res.json();
  // Response envelope: { response: { data: { id: "<mutamerId>" } } }
  const mutamerId = step2Json.response.data.id;
  log("submitToMasar [2/6] — mutamerId:", mutamerId);

  // ── Step 3: GetPersonalAndContactInfos ───────────────────────────────────
  // Must run before Attachment/Upload (matches the order observed in the browser HAR).
  // Fetches the server-assigned personalPictureId (the server reassigns the ID from step 1).
  log("submitToMasar [3/6] — GetPersonalAndContactInfos, mutamerId:", mutamerId);
  const encodedMutamerId = encodeURIComponent(mutamerId);
  const step3Res = await masarFetch(
    `https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/GetPersonalAndContactInfos?Id=${encodedMutamerId}`,
    { method: "POST", body: "{}" }
  );
  log("submitToMasar [3/6] — status:", step3Res.status);
  if (!step3Res.ok) {
    throw taggedError(
      step3Res.status === 401 ? "masar-auth" : null,
      S.ERR_FETCH_CONTACT(step3Res.status),
    );
  }
  const step3Json = await step3Res.json();
  const currentPersonalInfo = step3Json.response.data.personalInfo;
  log("submitToMasar [3/6] — personalPictureId:", currentPersonalInfo?.personalPictureId);

  // ── Step 4: Attachment/Upload (vaccination = passport image) ─────────────
  // Note: this is common_apis, not groups_apis.
  // Brief pause before upload — Masar/Cloudflare enforces a per-session
  // rate limit on Attachment/Upload. 4 s is enough to clear the burst window
  // between sequential submissions without noticeably slowing down a single one.
  await new Promise((r) => setTimeout(r, 4000));

  log("submitToMasar [4/6] — Attachment/Upload");
  const fd4 = new FormData();
  fd4.append("type", "3");
  fd4.append("file", imageBlob, imageName);
  let step4Res;
  for (let attempt = 0; attempt < 3; attempt++) {
    step4Res = await masarFetchMultipart(
      "https://masar.nusuk.sa/umrah/common_apis/api/Attachment/Upload",
      fd4
    );
    log("submitToMasar [4/6] — status:", step4Res.status, "attempt:", attempt + 1);
    if (step4Res.status !== 429) break;
    const retryAfter = parseInt(step4Res.headers.get("Retry-After") || "10", 10);
    logError(`submitToMasar [4/6] — 429, waiting ${retryAfter}s before retry`);
    await new Promise((r) => setTimeout(r, retryAfter * 1000));
  }
  if (!step4Res.ok) {
    const errText = await step4Res.text();
    logError("submitToMasar [4/6] — error body:", errText);
    throw taggedError(
      step4Res.status === 401 ? "masar-auth" : null,
      S.ERR_UPLOAD_ATTACH(step4Res.status),
    );
  }
  const step4Json = await step4Res.json();
  // Response envelope: { response: { data: { attachmentResponse: {...} } } }
  if (!step4Json.response || !step4Json.response.data) {
    const traceError = step4Json.traceError || step4Json.TraceError || "unknown";
    logError("submitToMasar [4/6] — Attachment/Upload returned no data. traceError:", traceError);
    throw new Error(S.ERR_UPLOAD_NO_DATA);
  }
  const vaccinationMeta = step4Json.response.data.attachmentResponse;
  log("submitToMasar [4/6] — vaccinationMeta id:", vaccinationMeta?.id);

  // ── Step 5: SubmitPersonalAndContactInfos ─────────────────────────────────
  log("submitToMasar [5/6] — SubmitPersonalAndContactInfos");
  const phoneCC = parseInt(settings.agency_phone_country_code || "966", 10);
  const phoneNo = settings.agency_phone || "";
  // Text fields from passport-core; numeric IDs from scan; image IDs from steps 3/4.
  const step5Body = {
    id: mutamerId,
    firstName:  { en: firstEn  || scan.firstNameEn,  ar: firstAr  || scan.firstNameAr  || null },
    secondName: { en: secondEn || scan.secondNameEn, ar: secondAr || scan.secondNameAr || null },
    thirdName:  { en: thirdEn  || scan.thirdNameEn,  ar: thirdAr  || scan.thirdNameAr  || null },
    familyName: { en: familyEn || scan.familyNameEn, ar: familyAr || scan.familyNameAr || null },
    martialStatusId,  // age-based: ≤20 → 1 (Single), >20 → 2 (Married); "martial" is masar's typo
    birthDate: coreBirthDate || scan.birthDate,
    profession: sanitiseArName(core.ProfessionAr) || sanitiseEnName(core.ProfessionEn) || scan.profession || "",
    gender: coreGender ?? scan.gender,
    personalPictureId: currentPersonalInfo.personalPictureId,
    personalPicture: currentPersonalInfo.personalPicture,
    residencyPictureId: null,
    residencyPicture: null,
    residencyNumber: null,
    residencyExpirationDate: null,
    vaccinationPictureId: vaccinationMeta.id,
    vaccinationPicture: {
      id: vaccinationMeta.id,
      fileName: vaccinationMeta.fileName,
      fileSize: vaccinationMeta.fileSize,
      fileExtension: vaccinationMeta.fileExtension,
      showDelete: true,
    },
    email: settings.agency_email || "",
    phone: { countryCode: phoneCC, phoneNumber: phoneNo },
    mobileCountryKey: phoneCC,
    mobileNo: phoneNo,
    postalCode: null,
    poBox: "",
    birthCountryId: scan.nationalityId,
    birthCityName: sanitiseArName(core.BirthCityAr) || sanitiseEnName(core.BirthCityEn) || scan.birthCity || "",
  };
  const step5Res = await masarFetch(
    "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/SubmitPersonalAndContactInfos",
    { method: "POST", body: JSON.stringify(step5Body) }
  );
  log("submitToMasar [5/6] — status:", step5Res.status);
  if (!step5Res.ok) {
    throw taggedError(
      step5Res.status === 401 ? "masar-auth" : null,
      S.ERR_SUBMIT_PERSONAL(step5Res.status),
    );
  }

  // ── Step 6: SubmitDisclosureForm ──────────────────────────────────────────
  log("submitToMasar [6/6] — SubmitDisclosureForm");
  // Questions 12 and 13 require placeholder detailedAnswers even when answer=false.
  // Question 16 also requires a placeholder detailedAnswers: [{}] (observed in HAR).
  const step6Body = {
    muamerInformationId: mutamerId,
    answers: [
      { questionId: 1,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 2,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 3,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 4,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 5,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 6,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 7,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 8,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 9,  answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 10, answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 11, answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 12, answer: false, simpleReason: null, detailedAnswers: [{ relativeName: null, relationId: null }] },
      { questionId: 13, answer: false, simpleReason: null, detailedAnswers: [{ travelFromDate: null, travelToDate: null, reasonOfTravel: null, countryId: null }] },
      { questionId: 14, answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 15, answer: false, simpleReason: null, detailedAnswers: [] },
      { questionId: 16, answer: false, simpleReason: null, detailedAnswers: [{}] },
    ],
  };
  const step6Res = await masarFetch(
    "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/SubmitDisclosureForm",
    { method: "POST", body: JSON.stringify(step6Body) }
  );
  log("submitToMasar [6/6] — status:", step6Res.status);
  if (!step6Res.ok) {
    throw taggedError(
      step6Res.status === 401 ? "masar-auth" : null,
      S.ERR_SUBMIT_DISCLOSURE(step6Res.status),
    );
  }

  let masarDetailId = null;
  const passportNumber = core.PassportNumber || scan.passportNumber || record.passport_number || null;
  if (passportNumber) {
    const listRes = await masarFetch(
      "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/GetMutamerList",
      {
        method: "POST",
        body: JSON.stringify({
          limit: 10,
          offset: 0,
          noCount: true,
          sortColumn: null,
          sortCriteria: [],
          filterList: [
            {
              propertyName: "passportNumber",
              operation: "match",
              propertyValue: passportNumber,
            },
          ],
        }),
      },
    );
    if (listRes.ok) {
      const listPayload = await listRes.json();
      masarDetailId = listPayload?.response?.data?.content?.[0]?.id ?? null;
    }
  }

  log("submitToMasar — all 7 steps complete! mutamerId:", mutamerId, "detailId:", masarDetailId);
  return { mutamerId, scanResult: scanData, masarDetailId };
}

// ─── Message handler (from popup) ────────────────────────────────────────────

function getContractState(contractEndDate) {
  if (!contractEndDate) {
    return "unknown";
  }
  const now = new Date();
  const end = new Date(contractEndDate);
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const endDayStart = new Date(end.getFullYear(), end.getMonth(), end.getDate());
  if (todayStart > endDayStart) return "expired";
  if (todayStart.getTime() === endDayStart.getTime()) return "expires-today";
  return "active";
}

async function storeContractSnapshot(contracts) {
  if (!contracts.length) {
    return;
  }
  const stored = await localGet(["masar_contract_id"]);
  const active = contracts.find((contract) => String(contract.contractId) === stored.masar_contract_id)
    || contracts.find((contract) => contract.contractStatus?.id === 0)
    || contracts[0];
  await localSet({
    masar_contract_id: String(active.contractId),
    masar_contract_number: active.contractNumber || "",
    masar_contract_name_en: active.companyNameEn || "",
    masar_contract_name_ar: active.companyNameAr || "",
    masar_contract_end_date: active.contractEndDate || "",
    masar_contract_status_name: active.contractStatus?.name || "",
    masar_contract_state: getContractState(active.contractEndDate),
  });
}

async function processRecordSubmission(record) {
  try {
    const { mutamerId, scanResult, masarDetailId } = await submitToMasar(record);
    await patchRecordStatus(record.upload_id, {
      status: "submitted",
      masar_mutamer_id: String(mutamerId),
      masar_scan_result: scanResult,
      masar_detail_id: masarDetailId ? String(masarDetailId) : null,
    });
    await localSet({ session_expired: false });
    return { ok: true, mutamerId, masarDetailId };
  } catch (error) {
    logError("processRecordSubmission — failed:", error.message);
    if (error.failureKind === "backend-auth" || error.failureKind === "masar-auth") {
      await localSet({ session_expired: true });
      await Notifications.notify(Notifications.NOTIFICATION_TYPES.SESSION_EXPIRED, S.NOTIF_SESSION_EXPIRED);
    }
    try {
      await patchRecordStatus(record.upload_id, {
        status: "failed",
        masar_mutamer_id: null,
        masar_scan_result: null,
        masar_detail_id: null,
      });
    } catch (patchError) {
      logError("processRecordSubmission — failed to patch failed status:", patchError.message);
    }
    return { ok: false, error: error.message, failureKind: error.failureKind || null };
  }
}

function shouldStopBatchAfterResult(result) {
  return result?.ok === false && (result.failureKind === "backend-auth" || result.failureKind === "masar-auth");
}

async function drainSubmissionBatch(uploadIds, providedRecords = new Map(), { notifyComplete = true } = {}) {
  const uniqueIds = [...new Set(uploadIds)];
  await sessionSet({
    submission_batch: uniqueIds,
    active_submit_id: null,
    submission_state:
      uniqueIds.length > 1 ? ContextChange.SUBMISSION_STATES.QUEUED_MORE : ContextChange.SUBMISSION_STATES.IDLE,
  });

  let processedCount = 0;
  let terminalFailure = null;
  for (const uploadId of uniqueIds) {
    const pendingStop = await ContextChange.shouldStopSubmission();
    if (pendingStop) {
      break;
    }

    const record = providedRecords.get(uploadId) || (await getRecordById(uploadId));
    if (!record || !shouldSubmitRecord(record)) {
      await removeFromBatch(uploadId);
      continue;
    }

    await sessionSet({ active_submit_id: uploadId });
    await ContextChange.setSubmissionState(ContextChange.SUBMISSION_STATES.SUBMITTING_CURRENT);
    const result = await processRecordSubmission(record);
    processedCount += 1;

    const remaining = await removeFromBatch(uploadId);
    await sessionSet({ active_submit_id: null });
    if (shouldStopBatchAfterResult(result)) {
      terminalFailure = result;
      break;
    }
    if (remaining.length > 0) {
      await ContextChange.setSubmissionState(ContextChange.SUBMISSION_STATES.QUEUED_MORE);
      if (await ContextChange.shouldStopSubmission()) {
        break;
      }
    }
  }

  const tail = await sessionGet(["submission_batch"]);
  if ((tail.submission_batch || []).length > 0) {
    await clearSubmissionBatch();
  } else {
    await ContextChange.setSubmissionState(ContextChange.SUBMISSION_STATES.IDLE);
  }
  const records = await fetchAllRecords();
  if (records.ok) {
    await updateBadge(records.data);
  } else {
    await updateBadgeState({ failedCount: 0 });
  }
  if (notifyComplete && processedCount > 0) {
    await Notifications.notify(Notifications.NOTIFICATION_TYPES.BATCH_COMPLETE, S.NOTIF_BATCH_COMPLETE);
  }
  if (terminalFailure) {
    return terminalFailure;
  }
  return { ok: true };
}

async function handleMessage(msg) {
  log("handleMessage — type:", msg.type);

  if (msg.type === "SYNC_SESSION") {
    return syncSession();
  }

  if (msg.type === "GROUP_LIST_CAPTURED") {
    await localSet({ masar_groups_cache: msg.data });
    return { ok: true };
  }

  if (msg.type === "CONTRACT_LIST_CAPTURED") {
    const contracts = msg.data?.response?.data?.contracts || [];
    await storeContractSnapshot(contracts);
    return { ok: true };
  }

  if (msg.type === "FETCH_GROUPS") {
    try {
      const cached = await localGet(["masar_groups_cache"]);
      if (cached.masar_groups_cache) {
        return { ok: true, data: cached.masar_groups_cache };
      }
      return { ok: true, data: await fetchGroups() };
    } catch (error) {
      return { ok: false, error: error.message || S.ERR_UNEXPECTED, failureKind: error.failureKind || null };
    }
  }

  if (msg.type === "FETCH_CONTRACTS") {
    try {
      const contracts = await fetchContracts();
      await storeContractSnapshot(contracts);
      return { ok: true, contracts };
    } catch (error) {
      return { ok: false, error: error.message || S.ERR_UNEXPECTED, failureKind: error.failureKind || null };
    }
  }

  if (msg.type === "FETCH_ALL_RECORDS") {
    return fetchAllRecords();
  }

  if (msg.type === "SUBMIT_BATCH") {
    const uploadIds = Array.isArray(msg.uploadIds) ? msg.uploadIds : [];
    return serialiseSubmit(() => drainSubmissionBatch(uploadIds, new Map()));
  }

  if (msg.type === "SUBMIT_RECORD") {
    const record = msg.record;
    if (!record?.upload_id) {
      return { ok: false, error: S.ERR_UNEXPECTED };
    }
    return serialiseSubmit(() =>
      drainSubmissionBatch([record.upload_id], new Map([[record.upload_id, record]]), { notifyComplete: false }),
    );
  }

  if (msg.type === "APPLY_CONTEXT_CHANGE") {
    await ContextChange.applyContextChange();
    await localRemove(["masar_contract_manual_override"]);
    await updateBadgeState();
    return { ok: true };
  }

  if (msg.type === "MARK_REVIEWED") {
    const patchRes = await apiFetch(`/records/${msg.uploadId}/review-status`, {
      method: "PATCH",
      body: JSON.stringify({ status: "reviewed" }),
    });
    if (!patchRes.ok) {
      return {
        ok: false,
        status: patchRes.status,
        failureKind: patchRes.status === 401 ? "backend-auth" : null,
      };
    }
    return { ok: true };
  }

  if (msg.type === "OPEN_MASAR") {
    await chrome.tabs.create({ url: "https://masar.nusuk.sa/pub/login" });
    return { ok: true };
  }

  return { ok: false, error: "unsupported-message" };
}

function startBackground() {
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    handleMessage(msg)
      .then(sendResponse)
      .catch((error) => {
        logError("handleMessage — unhandled rejection:", error.message);
        sendResponse({ ok: false, error: error.message });
      });
    return true;
  });

  if (chrome.runtime.onInstalled) {
    chrome.runtime.onInstalled.addListener(() => {
      void clearSubmissionBatch();
    });
  }
  if (chrome.runtime.onStartup) {
    chrome.runtime.onStartup.addListener(() => {
      void clearSubmissionBatch();
    });
  }
}

if (typeof module === "object" && module.exports) {
  module.exports = {
    countFailedRecords,
    handleMessage,
    shouldStopBatchAfterResult,
    shouldSubmitRecord,
  };
}

if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
  startBackground();
}
