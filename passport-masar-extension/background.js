// ─── Header capture ───────────────────────────────────────────────────────────
// Passively observe every outgoing request to masar and persist entity headers.
chrome.webRequest.onSendHeaders.addListener(
  (details) => {
    const h = {};
    details.requestHeaders.forEach((r) => { h[r.name.toLowerCase()] = r.value; });
    if (h["activeentityid"]) {
      chrome.storage.local.set({
        masar_entity_id: h["activeentityid"],
        masar_entity_type_id: h["activeentitytypeid"] || "",
        masar_contract_id: h["contractid"] || "",
      });
    }
  },
  { urls: ["https://masar.nusuk.sa/*", "https://*.nusuk.sa/*"] },
  ["requestHeaders", "extraHeaders"]
);

// ─── Masar API helpers ────────────────────────────────────────────────────────

async function getMasarEntityHeaders() {
  return new Promise((resolve) => {
    chrome.storage.local.get(
      ["masar_entity_id", "masar_entity_type_id", "masar_contract_id"],
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
  return {
    activeentityid: stored.masar_entity_id || "",
    activeentitytypeid: stored.masar_entity_type_id || "",
    contractid: stored.masar_contract_id || "",
    "entity-id": stored.masar_entity_id || "",
    "Content-Type": "application/json",
    accept: "application/json, text/plain, */*",
    "accept-language": "en",
  };
}

// All masar fetches must use credentials:'include' so the browser attaches
// the user's session cookies automatically.
async function masarFetch(url, options = {}) {
  const entityHeaders = await buildMasarHeaders();
  const { headers: extraHeaders, ...rest } = options;
  return fetch(url, {
    credentials: "include",
    ...rest,
    headers: { ...entityHeaders, ...(extraHeaders || {}) },
  });
}

// Multipart variant — omits Content-Type so the browser sets the boundary.
async function masarFetchMultipart(url, body) {
  const stored = await getMasarEntityHeaders();
  return fetch(url, {
    method: "POST",
    credentials: "include",
    headers: {
      activeentityid: stored.masar_entity_id || "",
      activeentitytypeid: stored.masar_entity_type_id || "",
      contractid: stored.masar_contract_id || "",
      "entity-id": stored.masar_entity_id || "",
      accept: "application/json, text/plain, */*",
      "accept-language": "en",
    },
    body,
  });
}

async function checkMasarSession() {
  try {
    const stored = await getMasarEntityHeaders();
    if (!stored.masar_entity_id) return { ok: false, reason: "no_entity_ids" };
    const res = await masarFetch(
      "https://masar.nusuk.sa/umrah/groups_apis/api/Groups/GroupsStatistics",
      { method: "POST", body: "{}" }
    );
    return { ok: res.ok, status: res.status };
  } catch {
    return { ok: false, reason: "network_error" };
  }
}

async function fetchGroups() {
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
  if (!res.ok) throw new Error(`groups ${res.status}`);
  return res.json();
}

// ─── Passport-API helpers ─────────────────────────────────────────────────────

async function getApiToken() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["api_token"], (items) => resolve(items.api_token || null));
  });
}

async function apiFetch(path, options = {}) {
  const token = await getApiToken();
  const stored = await new Promise((resolve) =>
    chrome.storage.local.get(["api_base_url"], resolve)
  );
  const base = stored.api_base_url || "";
  const res = await fetch(`${base}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  return res;
}

// ─── Submission workflow ──────────────────────────────────────────────────────

async function fetchImageBytes(uri) {
  const token = await getApiToken();
  const res = await fetch(uri, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`image fetch failed: ${res.status}`);
  return res.arrayBuffer();
}

async function submitToMasar(record) {
  const settings = await new Promise((resolve) =>
    chrome.storage.local.get(["agency_email", "agency_phone", "agency_phone_country_code"], resolve)
  );

  const imageName = record.filename || "passport.jpg";
  const imageBytes = await fetchImageBytes(record.passport_image_uri);
  const imageBlob = new Blob([imageBytes], { type: "image/jpeg" });

  // ── Step 1: ScanPassport ──────────────────────────────────────────────────
  const step1Form = new FormData();
  step1Form.append("passportImage", imageBlob, imageName);
  const step1Res = await masarFetchMultipart(
    "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/ScanPassport",
    step1Form
  );
  if (!step1Res.ok) throw new Error(`ScanPassport failed: ${step1Res.status}`);
  const step1Json = await step1Res.json();
  // Response envelope: { response: { data: { passportResponse: {...}, ... } } }
  const scanData = step1Json.response.data;
  const scan = scanData.passportResponse;
  const passportImageMeta = scan.passportImage;
  const personalPictureMeta = scan.personalPicture;

  // ── Step 2: SubmitPassportInforamtionWithNationality ──────────────────────
  // Note: only firstName + familyName in EN are sent here; AR names go in step 4
  const step2Body = {
    id: null,
    firstName: { en: scan.firstNameEn },
    familyName: { en: scan.familyNameEn },
    previousNationalityId: null,
    gender: scan.gender,
    passportTypeId: 1,
    birthDate: scan.birthDate,
    passportExpiryDate: scan.passportExpiryDate,
    passportIssueDate: scan.passportIssueDate,
    nationalityId: scan.nationalityId,
    issueCountryId: scan.countryId,
    passportNumber: scan.passportNumber,
    issueCityName: scan.issueCity || "",
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
  if (!step2Res.ok) throw new Error(`SubmitPassport failed: ${step2Res.status}`);
  const step2Json = await step2Res.json();
  // Response envelope: { response: { data: { id: "<mutamerId>" } } }
  const mutamerId = step2Json.response.data.id;

  // ── Step 3: Attachment/Upload (vaccination = passport image) ─────────────
  // Note: this is common_apis, not groups_apis
  const step3Form = new FormData();
  step3Form.append("type", "3");
  step3Form.append("file", imageBlob, imageName);
  const step3Res = await masarFetchMultipart(
    "https://masar.nusuk.sa/umrah/common_apis/api/Attachment/Upload",
    step3Form
  );
  if (!step3Res.ok) throw new Error(`Attachment upload failed: ${step3Res.status}`);
  const step3Json = await step3Res.json();
  // Response envelope: { response: { data: { attachmentResponse: {...} } } }
  const vaccinationMeta = step3Json.response.data.attachmentResponse;

  // ── Step 3.5: GetPersonalAndContactInfos ─────────────────────────────────
  // Fetch to get the server-assigned personalPictureId (differs from scan ID)
  const encodedMutamerId = encodeURIComponent(mutamerId);
  const step35Res = await masarFetch(
    `https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/GetPersonalAndContactInfos?Id=${encodedMutamerId}`,
    { method: "POST", body: "{}" }
  );
  if (!step35Res.ok) throw new Error(`GetPersonalAndContactInfos failed: ${step35Res.status}`);
  const step35Json = await step35Res.json();
  const currentPersonalInfo = step35Json.response.data.personalInfo;

  // ── Step 4: SubmitPersonalAndContactInfos ─────────────────────────────────
  const phoneCC = parseInt(settings.agency_phone_country_code || "966", 10);
  const phoneNo = settings.agency_phone || "";
  const step4Body = {
    id: mutamerId,
    firstName: { en: scan.firstNameEn, ar: scan.firstNameAr },
    secondName: { en: scan.secondNameEn, ar: scan.secondNameAr },
    thirdName: { en: scan.thirdNameEn, ar: scan.thirdNameAr },
    familyName: { en: scan.familyNameEn, ar: scan.familyNameAr },
    martialStatusId: 2,  // Married — field is "martial" not "marital" (masar typo)
    birthDate: scan.birthDate,
    profession: scan.profession || "",
    gender: scan.gender,
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
    birthCountryId: scan.countryId,
    birthCityName: scan.birthCity || "",
  };
  const step4Res = await masarFetch(
    "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/SubmitPersonalAndContactInfos",
    { method: "POST", body: JSON.stringify(step4Body) }
  );
  if (!step4Res.ok) throw new Error(`SubmitPersonal failed: ${step4Res.status}`);

  // ── Step 5: SubmitDisclosureForm ──────────────────────────────────────────
  // Each answer requires questionId + simpleReason + detailedAnswers.
  // Questions 12 and 13 require placeholder detailedAnswers even when answer=false.
  const step5Body = {
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
      { questionId: 16, answer: false, simpleReason: null, detailedAnswers: [] },
    ],
  };
  const step5Res = await masarFetch(
    "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/SubmitDisclosureForm",
    { method: "POST", body: JSON.stringify(step5Body) }
  );
  if (!step5Res.ok) throw new Error(`SubmitDisclosure failed: ${step5Res.status}`);

  return { mutamerId, scanResult: scanData };
}

// ─── Message handler (from popup) ────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  handleMessage(msg).then(sendResponse);
  return true; // keep channel open for async response
});

async function handleMessage(msg) {
  if (msg.type === "CHECK_SESSION") {
    return checkMasarSession();
  }

  if (msg.type === "FETCH_GROUPS") {
    try {
      const data = await fetchGroups();
      return { ok: true, data };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }

  if (msg.type === "FETCH_PENDING") {
    try {
      const res = await apiFetch("/records/masar/pending");
      if (!res.ok) return { ok: false, status: res.status };
      const data = await res.json();
      return { ok: true, data };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }

  if (msg.type === "SUBMIT_RECORD") {
    const record = msg.record;
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
      if (!patchRes.ok) throw new Error(`patch failed: ${patchRes.status}`);
      return { ok: true, mutamerId };
    } catch (err) {
      apiFetch(`/records/${record.upload_id}/masar-status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "failed", masar_mutamer_id: null, masar_scan_result: null }),
      }).catch(() => {});
      return { ok: false, error: err.message };
    }
  }

  if (msg.type === "OPEN_MASAR") {
    chrome.tabs.create({ url: "https://masar.nusuk.sa/" });
    return { ok: true };
  }
}
