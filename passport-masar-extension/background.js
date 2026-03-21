importScripts("config.js");
importScripts("strings.js");

// ─── Header capture ───────────────────────────────────────────────────────────
// Passively observe every outgoing request to masar and persist entity headers.
chrome.webRequest.onSendHeaders.addListener(
  (details) => {
    const h = {};
    details.requestHeaders.forEach((r) => { h[r.name.toLowerCase()] = r.value; });
    if (h["activeentityid"]) {
      // Only update each key when the header is actually present — never overwrite with empty.
      const update = { masar_entity_id: h["activeentityid"] };
      if (h["activeentitytypeid"]) update.masar_entity_type_id = h["activeentitytypeid"];
      if (h["contractid"])         update.masar_contract_id    = h["contractid"];
      // Only capture Authorization when activeentityid is also present.
      // Requests with activeentityid use tokenType:5 (the correct session token).
      // Requests without activeentityid (e.g. initial login) use tokenType:3,
      // which causes "No Active Contract" errors if stored.
      if (h["authorization"]) {
        const authVal = h["authorization"].replace(/^"|"$/g, "");
        update.masar_auth_token = authVal;
        log("Captured Authorization (tokenType:5, first 30):", authVal.slice(0, 30) + "...");
        // Decode JWT payload to extract user name — avoids needing a separate API call.
        try {
          const payload = JSON.parse(atob(authVal.replace(/^Bearer\s+/i, "").split(".")[1]));
          if (payload.name) update.masar_user_name = payload.name;
        } catch (_) {}
      }
      log("Captured entity headers — entityId:", h["activeentityid"],
          "entityTypeId:", h["activeentitytypeid"], "contractId:", h["contractid"]);
      chrome.storage.local.set(update);
    }
  },
  { urls: ["https://masar.nusuk.sa/*", "https://*.nusuk.sa/*"] },
  ["requestHeaders", "extraHeaders"]
);

// ─── Badge ────────────────────────────────────────────────────────────────────

function updateBadge(records) {
  const failed = records.filter((r) => r.masar_status === "failed").length;
  if (failed > 0) {
    chrome.action.setBadgeText({ text: String(failed) });
    chrome.action.setBadgeBackgroundColor({ color: "#e53e3e" });
  } else {
    chrome.action.setBadgeText({ text: "" });
  }
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

    // Detect entity or contract switch — if either changed, the stored group
    // belongs to the old context and must be cleared.
    const existing = await new Promise((resolve) =>
      chrome.storage.local.get(["masar_entity_id", "masar_contract_id"], resolve)
    );
    const entityChanged  = existing.masar_entity_id   && s.entityId   && existing.masar_entity_id   !== s.entityId;
    const contractChanged = existing.masar_contract_id && s.contractId && existing.masar_contract_id !== s.contractId;
    if (entityChanged || contractChanged) {
      log("syncSessionFromMasar — context changed (entity or contract), clearing group selection");
      chrome.storage.local.remove(["masar_group_id", "masar_group_name", "masar_group_number", "masar_groups_cache"]);
    }

    const update = {};
    if (s.entityId)           update.masar_entity_id            = s.entityId;
    if (s.entityTypeId)       update.masar_entity_type_id       = s.entityTypeId;
    if (s.contractId)         update.masar_contract_id          = s.contractId;
    if (s.contractNumber)     update.masar_contract_number      = s.contractNumber;
    if (s.contractNameEn)     update.masar_contract_name_en     = s.contractNameEn;
    if (s.contractNameAr)     update.masar_contract_name_ar     = s.contractNameAr;
    if (s.contractEndDate)    update.masar_contract_end_date    = s.contractEndDate;
    if (s.contractStatusName) update.masar_contract_status_name = s.contractStatusName;
    // masar_user_name is decoded from JWT in the webRequest listener — not sourced here.
    update.masar_contract_state = contractState;
    // Do NOT sync jwt — webRequest captures tokenType:5; pms-tk_session is tokenType:3.
    if (Object.keys(update).length) chrome.storage.local.set(update);
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
    chrome.storage.local.set({ masar_last_synced: Date.now() });
    const stored = await getMasarEntityHeaders();
    log("syncSession — entityId:", stored.masar_entity_id, "contractId:", stored.masar_contract_id, "hasAuthToken:", !!stored.masar_auth_token);
    return { ok: true };
  } catch (err) {
    logError("syncSession — error:", err.message);
    return { ok: true }; // non-fatal
  }
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
  if (!res.ok) throw new Error(`groups ${res.status}`);
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

// ─── Submission workflow ──────────────────────────────────────────────────────

async function fetchImageBytes(uploadId) {
  log("fetchImageBytes — upload_id:", uploadId);
  const res = await apiFetch(`/records/${uploadId}/image`);
  if (!res.ok) throw new Error(S.ERR_IMAGE_FETCH(res.status));
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

async function submitToMasar(record) {
  const settings = await new Promise((resolve) =>
    chrome.storage.local.get(["agency_email", "agency_phone", "agency_phone_country_code"], resolve)
  );

  // passport-core OCR data — used for all text fields (better quality than ScanPassport OCR).
  // ScanPassport is still called for image uploads and numeric IDs it returns.
  const core = record.core_result?.data || {};
  log("submitToMasar — core_result fields available:", Object.keys(core).filter((k) => core[k]));

  const firstEn  = sanitiseEnName(core.FirstNameEn);
  const secondEn = sanitiseEnName(core.FatherNameEn);
  const thirdEn  = sanitiseEnName(core.GrandfatherNameEn);
  const firstAr  = sanitiseArName(core.FirstNameAr);
  const secondAr = sanitiseArName(core.FatherNameAr);
  const thirdAr  = sanitiseArName(core.GrandfatherNameAr);
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
    throw new Error(S.ERR_SCAN_PASSPORT(step1Res.status));
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
  if (!step2Res.ok) throw new Error(S.ERR_SUBMIT_PASSPORT(step2Res.status));
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
  if (!step3Res.ok) throw new Error(S.ERR_FETCH_CONTACT(step3Res.status));
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
    throw new Error(S.ERR_UPLOAD_ATTACH(step4Res.status));
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
  if (!step5Res.ok) throw new Error(S.ERR_SUBMIT_PERSONAL(step5Res.status));

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
  if (!step6Res.ok) throw new Error(S.ERR_SUBMIT_DISCLOSURE(step6Res.status));

  log("submitToMasar — all 6 steps complete! mutamerId:", mutamerId);
  return { mutamerId, scanResult: scanData };
}

// ─── Message handler (from popup) ────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  handleMessage(msg)
    .then(sendResponse)
    .catch((err) => {
      logError("handleMessage — unhandled rejection:", err.message);
      sendResponse({ ok: false, error: err.message });
    });
  return true; // keep channel open for async response
});

async function handleMessage(msg) {
  log("handleMessage — type:", msg.type);

  if (msg.type === "SYNC_SESSION") {
    return syncSession();
  }

  if (msg.type === "GROUP_LIST_CAPTURED") {
    log("GROUP_LIST_CAPTURED — storing group list cache");
    chrome.storage.local.set({ masar_groups_cache: msg.data });
    return { ok: true };
  }

  if (msg.type === "CONTRACT_LIST_CAPTURED") {
    // Content script intercepted GetContractList. Find the contract matching the
    // currently active contractId and store its display details.
    const contracts = msg.data?.response?.data?.contracts || [];
    log("CONTRACT_LIST_CAPTURED —", contracts.length, "contracts");
    if (contracts.length === 0) return { ok: true };

    const stored = await new Promise((resolve) =>
      chrome.storage.local.get(["masar_contract_id"], resolve)
    );
    // Match the active contract. If no contractId stored yet, take the first active one.
    const active = contracts.find((c) => String(c.contractId) === stored.masar_contract_id)
      || contracts.find((c) => c.contractStatus?.id === 0)
      || contracts[0];

    const now = new Date();
    const end = active.contractEndDate ? new Date(active.contractEndDate) : null;
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    let contractState = "unknown";
    if (end) {
      const endDayStart = new Date(end.getFullYear(), end.getMonth(), end.getDate());
      if (todayStart > endDayStart) contractState = "expired";
      else if (todayStart.getTime() === endDayStart.getTime()) contractState = "expires-today";
      else contractState = "active";
    }

    chrome.storage.local.set({
      masar_contract_id:          String(active.contractId),
      masar_contract_number:      active.contractNumber || "",
      masar_contract_name_en:     active.companyNameEn || "",
      masar_contract_name_ar:     active.companyNameAr || "",
      masar_contract_end_date:    active.contractEndDate || "",
      masar_contract_status_name: active.contractStatus?.name || "",
      masar_contract_state:       contractState,
    });
    log("CONTRACT_LIST_CAPTURED — stored contract:", active.companyNameEn, "state:", contractState);
    return { ok: true };
  }

  if (msg.type === "FETCH_GROUPS") {
    try {
      // 1. Use cached response if available (captured via content script intercept)
      const cached = await new Promise((resolve) =>
        chrome.storage.local.get(["masar_groups_cache"], resolve)
      );
      if (cached.masar_groups_cache) {
        log("FETCH_GROUPS — using cached group list");
        return { ok: true, data: cached.masar_groups_cache };
      }
      // 2. Fall back to direct API call (may fail with 520 due to Cloudflare)
      const data = await fetchGroups();
      log("FETCH_GROUPS — returning live data");
      return { ok: true, data };
    } catch (err) {
      logError("FETCH_GROUPS — error:", err.message);
      return { ok: false, error: S.ERR_UNEXPECTED };
    }
  }

  if (msg.type === "FETCH_PENDING") {
    try {
      const res = await apiFetch("/records/masar/pending");
      log("FETCH_PENDING — status:", res.status);
      if (!res.ok) return { ok: false, status: res.status };
      const data = await res.json();
      log("FETCH_PENDING — count:", Array.isArray(data) ? data.length : data);
      updateBadge(Array.isArray(data) ? data : []);
      return { ok: true, data };
    } catch (err) {
      logError("FETCH_PENDING — error:", err.message);
      return { ok: false, error: S.ERR_UNEXPECTED };
    }
  }

  if (msg.type === "SUBMIT_RECORD") {
    const record = msg.record;
    log("SUBMIT_RECORD — upload_id:", record.upload_id);
    return serialiseSubmit(async () => {
    try {
      const { mutamerId, scanResult } = await submitToMasar(record);
      const patchRes = await apiFetch(`/records/${record.upload_id}/masar-status`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "submitted",
          masar_mutamer_id: String(mutamerId),
          masar_scan_result: scanResult,
        }),
      });
      log("SUBMIT_RECORD — patch status:", patchRes.status);
      if (!patchRes.ok) throw new Error(S.ERR_PATCH_FAILED(patchRes.status));
      // Refresh badge after successful submit — failure count may have dropped.
      apiFetch("/records/masar/pending").then(async (r) => {
        if (r.ok) updateBadge(await r.json());
      }).catch(() => {});
      return { ok: true, mutamerId };
    } catch (err) {
      logError("SUBMIT_RECORD — failed:", err.message);
      apiFetch(`/records/${record.upload_id}/masar-status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "failed", masar_mutamer_id: null, masar_scan_result: null }),
      }).then(async () => {
        // Refresh badge so the new failure shows immediately.
        const r = await apiFetch("/records/masar/pending");
        if (r.ok) updateBadge(await r.json());
      }).catch(() => {});
      return { ok: false, error: err.message };
    }
    }); // end serialiseSubmit
  }

  if (msg.type === "OPEN_MASAR") {
    chrome.tabs.create({ url: "https://masar.nusuk.sa/pub/login" });
    return { ok: true };
  }
}
