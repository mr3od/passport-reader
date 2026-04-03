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
        const authVal = normalizeMasarAuthorizationHeader(h["authorization"]);
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
    (record) =>
      record.upload_status === "failed"
      || record.masar_status === "failed"
      || record.masar_status === "missing",
  ).length;
}

function taggedError(failureKind, message, metadata = null) {
  const error = new Error(message);
  if (failureKind) {
    error.failureKind = failureKind;
  }
  if (metadata && typeof metadata === "object") {
    Object.assign(error, metadata);
  }
  return error;
}

// ─── Submission serializer ────────────────────────────────────────────────────
// Only one SUBMIT_RECORD runs at a time. Concurrent calls queue behind the
// current one — prevents parallel Attachment/Upload 429s from Cloudflare and
// ensures no orphaned partial mutamers are left in Masar.
let _submitChain = Promise.resolve();
let _isDrainingSubmissions = false;
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

const MASAR_TAB_URLS = ["https://masar.nusuk.sa/*", "https://*.nusuk.sa/*"];
const MASAR_ENTRY_URL = "https://masar.nusuk.sa/pub/login";
const RECENTLY_CLOSED_DETAILS_TABS = new Map();

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

async function queryMasarTabs() {
  const tabs = await chrome.tabs.query({ url: MASAR_TAB_URLS });
  log("[details experiment] queryMasarTabs", { count: tabs.length });
  return tabs;
}

function isMasarAppTab(tab) {
  const url = typeof tab?.url === "string" ? tab.url : "";
  return url.includes("/umrah/") && !url.includes("/pub/");
}

function selectSourceMasarTab(tabs) {
  const allTabs = Array.isArray(tabs) ? tabs.filter((tab) => typeof tab?.id === "number") : [];
  const rankedPools = [
    allTabs.filter((tab) => tab.active && isMasarAppTab(tab)),
    allTabs.filter((tab) => isMasarAppTab(tab)),
    allTabs.filter((tab) => tab.active),
    allTabs,
  ];
  for (const pool of rankedPools) {
    if (pool.length > 0) {
      return pool[0];
    }
  }
  return null;
}

function rankSourceMasarTabs(tabs) {
  const selected = selectSourceMasarTab(tabs);
  const allTabs = Array.isArray(tabs) ? tabs.filter((tab) => typeof tab?.id === "number") : [];
  if (!selected) {
    return allTabs;
  }
  return [selected, ...allTabs.filter((tab) => tab.id !== selected.id)];
}

async function focusWindow(windowId) {
  if (typeof windowId !== "number") {
    return;
  }
  await chrome.windows.update(windowId, { focused: true });
}

async function activateTab(tabId, windowId) {
  if (typeof tabId !== "number") {
    return;
  }
  await chrome.tabs.update(tabId, { active: true });
  await focusWindow(windowId);
}

async function getTabSnapshot(tabId) {
  if (typeof tabId !== "number") {
    return null;
  }
  try {
    const tab = await chrome.tabs.get(tabId);
    return tab ? {
      id: tab.id,
      windowId: tab.windowId,
      url: tab.url,
      pendingUrl: tab.pendingUrl,
      title: tab.title,
      status: tab.status,
    } : null;
  } catch (error) {
    const closedReason = RECENTLY_CLOSED_DETAILS_TABS.get(tabId);
    if (closedReason) {
      log("[details experiment] getTabSnapshot after expected tab close", {
        tabId,
        reason: closedReason,
      });
      return null;
    }
    logError("[details experiment] getTabSnapshot failed", {
      tabId,
      message: error?.message || String(error),
    });
    return null;
  }
}

async function logFinalTabUrl(tabId, delayMs = 1500) {
  await new Promise((resolve) => setTimeout(resolve, delayMs));
  if (typeof chrome === "undefined" || !chrome.tabs?.get) {
    return;
  }
  const snapshot = await getTabSnapshot(tabId);
  log("[details experiment] final tab", snapshot ? {
    id: snapshot.id,
    url: snapshot.url,
    status: snapshot.status,
    title: snapshot.title,
  } : null);
  await logClonedTabRuntimeState(tabId, "final-tab");
}

async function waitForTabUrl(tabId, predicate, { attempts = 10, delayMs = 250 } = {}) {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const snapshot = await getTabSnapshot(tabId);
    if (snapshot && predicate(snapshot)) {
      log("[details experiment] ready after poll", {
        tabId,
        attempt,
        url: snapshot.url,
      });
      return snapshot;
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return getTabSnapshot(tabId);
}

async function waitForMutamerDetailsRender(tabId, { attempts = 24, delayMs = 500 } = {}) {
  let lastSnapshot = null;
  let lastProbe = null;
  let lastOutcome = "unknown";
  let repeatedSessionExpired = 0;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const snapshot = await getTabSnapshot(tabId);
    const probe = await inspectMasarTabContent(tabId);
    const outcome = classifyMutamerDetailsOutcome(snapshot, probe);
    const isLoadComplete = snapshot?.status === "complete";
    lastSnapshot = snapshot;
    lastProbe = probe;
    lastOutcome = outcome;

    if (outcome === "mutamer-missing" && isLoadComplete) {
      log("[details experiment] terminal render outcome", {
        tabId,
        attempt,
        outcome,
        url: snapshot?.url || null,
        diagnostics: buildMutamerDetailsDiagnostics(snapshot, probe),
      });
      return { snapshot, probe, outcome };
    }
    if (outcome === "session-expired" && isLoadComplete) {
      const isHardLoginRoute = typeof snapshot?.url === "string" && snapshot.url.includes("/pub/login");
      repeatedSessionExpired = isHardLoginRoute ? 3 : repeatedSessionExpired + 1;
      if (repeatedSessionExpired >= 3) {
        log("[details experiment] terminal render outcome", {
          tabId,
          attempt,
          outcome,
          url: snapshot?.url || null,
          diagnostics: buildMutamerDetailsDiagnostics(snapshot, probe),
        });
        return { snapshot, probe, outcome };
      }
    } else {
      repeatedSessionExpired = 0;
    }

    if (
      outcome === "ready"
      && snapshot?.status === "complete"
      && typeof snapshot?.url === "string"
      && snapshot.url.includes("/umrah/mutamer/mutamer-details/")
    ) {
      log("[details experiment] render ready after poll", {
        tabId,
        attempt,
        url: snapshot.url,
      });
      return { snapshot, probe, outcome };
    }

    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return { snapshot: lastSnapshot, probe: lastProbe, outcome: lastOutcome };
}

function extractMutamerDetailId(clickUrl) {
  if (typeof clickUrl !== "string" || clickUrl.length === 0) {
    return null;
  }
  try {
    const parsed = new URL(clickUrl);
    const segments = parsed.pathname.split("/").filter(Boolean);
    const detailId = segments[segments.length - 1];
    return detailId ? decodeURIComponent(detailId) : null;
  } catch (_error) {
    return null;
  }
}

function normalizeMasarAuthorizationHeader(value) {
  if (typeof value !== "string") {
    return "";
  }
  let token = value.trim();
  if (!token) {
    return "";
  }
  token = token.replace(/^Bearer\s+/i, "");
  token = token.replace(/^['"]+|['"]+$/g, "");
  if (!token) {
    return "";
  }
  return `Bearer ${token}`;
}

function extractMasarContextFromSnapshot(snapshot) {
  const sessionEntries = Array.isArray(snapshot?.sessionEntries) ? snapshot.sessionEntries : [];
  const sessionMap = new Map(sessionEntries);
  let parsedContract = null;
  if (typeof snapshot?.localCurrentContract === "string") {
    try {
      parsedContract = JSON.parse(snapshot.localCurrentContract);
    } catch (_error) {
      parsedContract = null;
    }
  }
  const contractId = parsedContract?.contractId != null ? String(parsedContract.contractId) : "";
  return {
    entityId: sessionMap.get("pms-ac_En_Id") || "",
    entityTypeId: sessionMap.get("pms-ac_En_Type_Id") || "",
    authToken: sessionMap.get("pms-tk_session") || "",
    contractId,
    hasContract: Boolean(contractId),
  };
}

function buildStoredCurrentContractValue(record) {
  if (!record?.submission_contract_id) {
    return null;
  }
  const contractId = Number(record.submission_contract_id);
  return {
    contractNumber: record.submission_contract_number || "",
    contractId: Number.isFinite(contractId) ? contractId : record.submission_contract_id,
    contractStatus:
      typeof record.submission_contract_status === "boolean"
        ? record.submission_contract_status
        : true,
    uoSubscriptionStatusId:
      typeof record.submission_uo_subscription_status_id === "number"
        ? record.submission_uo_subscription_status_id
        : 1,
    companyNameAr: record.submission_contract_name_ar || record.submission_contract_name || "",
    companyNameEn: record.submission_contract_name_en || record.submission_contract_name || "",
  };
}

function buildStoredDetailsContextOverride(record) {
  const currentContract = buildStoredCurrentContractValue(record);
  if (!record?.submission_entity_id || !record?.submission_contract_id || !currentContract) {
    return null;
  }
  return {
    entityId: record.submission_entity_id,
    entityTypeId: record.submission_entity_type_id || "",
    contractId: record.submission_contract_id,
    currentContractRaw: JSON.stringify(currentContract),
  };
}

function applyDetailsContextOverrideToSnapshot(snapshot, override) {
  if (!override) {
    return snapshot;
  }
  const sessionMap = new Map(Array.isArray(snapshot?.sessionEntries) ? snapshot.sessionEntries : []);
  if (override.entityId) {
    sessionMap.set("pms-ac_En_Id", override.entityId);
  }
  if (override.entityTypeId) {
    sessionMap.set("pms-ac_En_Type_Id", override.entityTypeId);
  }
  return {
    sessionEntries: Array.from(sessionMap.entries()),
    localCurrentContract:
      typeof override.currentContractRaw === "string"
        ? override.currentContractRaw
        : snapshot?.localCurrentContract || null,
  };
}

function classifyMutamerDetailsOutcome(snapshot, probe) {
  const url = typeof snapshot?.url === "string" ? snapshot.url : "";
  const href = typeof probe?.href === "string" ? probe.href : "";
  const title = typeof probe?.title === "string" ? probe.title.toLowerCase() : "";
  const bodyText = typeof probe?.bodyText === "string" ? probe.bodyText.toLowerCase() : "";
  const combined = `${title}\n${bodyText}`;
  const loginSignals = [
    "login",
    "sign in",
    "تسجيل الدخول",
    "تسجيل دخول",
    "الدخول",
  ];
  const detailsSignals = [
    "passport",
    "جواز",
    "mutamer",
    "معتمر",
    "group",
    "المجموعة",
  ];
  const looksLikeLogin = loginSignals.some((signal) => combined.includes(signal));
  const looksLikeDetails = detailsSignals.some((signal) => combined.includes(signal));

  if (url.includes("/pub/login")) {
    return "session-expired";
  }
  if (url.includes("/pub/notfound") || href.includes("/pub/notfound")) {
    return "mutamer-missing";
  }
  if (looksLikeLogin && !looksLikeDetails) {
    return "session-expired";
  }
  if (url.includes("/umrah/mutamer/mutamer-details/")) {
    return "ready";
  }
  return "unknown";
}

async function inspectMasarTabContent(tabId) {
  if (typeof tabId !== "number" || !chrome.scripting?.executeScript) {
    return null;
  }
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => ({
        href: location.href,
        title: document.title,
        bodyText: (document.body?.innerText || "").slice(0, 400),
      }),
    });
    return results?.[0]?.result || null;
  } catch (error) {
    logError("[details experiment] inspectMasarTabContent failed", {
      tabId,
      message: error?.message || String(error),
    });
    return null;
  }
}

function buildMutamerDetailsDiagnostics(snapshot, probe) {
  const bodyText = typeof probe?.bodyText === "string" ? probe.bodyText : "";
  return {
    snapshotUrl: snapshot?.url || null,
    snapshotStatus: snapshot?.status || null,
    probeHref: probe?.href || null,
    probeTitle: probe?.title || null,
    bodySnippet: bodyText ? bodyText.slice(0, 240) : null,
  };
}

function truncateDebugValue(value, maxLength = 160) {
  if (typeof value !== "string") {
    return value;
  }
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}...`;
}

function formatCookieDebugSummary(cookies) {
  if (!Array.isArray(cookies)) {
    return cookies;
  }
  const summary = {};
  for (const cookie of cookies) {
    if (!cookie?.name) {
      continue;
    }
    summary[cookie.name] = {
      present: true,
      domain: cookie.domain || null,
      path: cookie.path || null,
      session: Boolean(cookie.session),
      expires: cookie.expirationDate || null,
      valuePreview: truncateDebugValue(cookie.value, 32),
    };
  }
  return summary;
}

async function captureClonedTabStorageState(tabId) {
  if (typeof tabId !== "number" || !chrome.scripting?.executeScript) {
    return null;
  }
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => ({
        href: location.href,
        sessionEntries: Object.entries(sessionStorage),
        localEntries: Object.entries(localStorage),
      }),
    });
    return results?.[0]?.result || null;
  } catch (error) {
    logError("[details experiment] captureClonedTabStorageState failed", {
      tabId,
      message: error?.message || String(error),
    });
    return null;
  }
}

async function captureMasarCookiesState() {
  if (typeof chrome === "undefined" || !chrome.cookies?.getAll) {
    return null;
  }
  try {
    const cookies = await chrome.cookies.getAll({ domain: "masar.nusuk.sa" });
    return cookies.map((cookie) => ({
      name: cookie.name,
      domain: cookie.domain,
      path: cookie.path,
      session: cookie.session,
      expirationDate: cookie.expirationDate || null,
      value: truncateDebugValue(cookie.value, 120),
    }));
  } catch (error) {
    logError("[details experiment] captureMasarCookiesState failed", {
      message: error?.message || String(error),
    });
    return null;
  }
}

async function logClonedTabRuntimeState(tabId, reason) {
  const [snapshot, storageState, cookies] = await Promise.all([
    getTabSnapshot(tabId),
    captureClonedTabStorageState(tabId),
    captureMasarCookiesState(),
  ]);
  log("[details experiment] cloned tab runtime state", {
    reason,
    tabId,
    snapshot,
    storage: storageState
      ? {
          href: storageState.href || null,
          sessionEntries: Array.isArray(storageState.sessionEntries)
            ? storageState.sessionEntries.map(([key, value]) => [key, truncateDebugValue(value)])
            : null,
          localEntries: Array.isArray(storageState.localEntries)
            ? storageState.localEntries.map(([key, value]) => [key, truncateDebugValue(value)])
            : null,
        }
      : null,
    cookies: formatCookieDebugSummary(cookies),
  });
}

async function handleMutamerDetailsOutcome(tabId) {
  const snapshot = await getTabSnapshot(tabId);
  const probe = await inspectMasarTabContent(tabId);
  const outcome = classifyMutamerDetailsOutcome(snapshot, probe);
  log("[details experiment] outcome", {
    tabId,
    outcome,
    url: snapshot?.url || null,
    title: probe?.title || snapshot?.title || null,
    diagnostics: buildMutamerDetailsDiagnostics(snapshot, probe),
  });

  return outcome;
}

async function navigateExistingMasarTab(tab, clickUrl) {
  if (!tab || typeof tab.id !== "number") {
    return false;
  }
  log("[details experiment] navigateExistingMasarTab start", {
    tabId: tab.id,
    windowId: tab.windowId,
    toUrl: clickUrl,
  });
  await chrome.tabs.update(tab.id, { url: clickUrl, active: true });
  await focusWindow(tab.windowId);
  log("[details experiment] navigateExistingMasarTab complete", {
    tabId: tab.id,
    toUrl: clickUrl,
  });
  return true;
}

async function openMasarEntryTab({ active = false } = {}) {
  const tab = await chrome.tabs.create({ url: MASAR_ENTRY_URL, active });
  log("[details experiment] openMasarEntryTab complete", {
    id: tab?.id,
    windowId: tab?.windowId,
    activeRequested: active,
  });
  return tab;
}

async function closeTabQuietly(tabId, reason = "unspecified") {
  if (typeof tabId !== "number") {
    return;
  }
  try {
    RECENTLY_CLOSED_DETAILS_TABS.set(tabId, reason);
    log("[details experiment] closing cloned tab", {
      tabId,
      reason,
    });
    await chrome.tabs.remove(tabId);
  } catch {}
}

async function captureMasarTabSnapshot(tabId) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({
      sessionEntries: Object.entries(sessionStorage),
      localCurrentContract: localStorage.getItem("currentContract"),
    }),
  });
  const snapshot = results?.[0]?.result || null;
  log("[details experiment] captureMasarTabSnapshot complete", {
    tabId,
    sessionKeys: Array.isArray(snapshot?.sessionEntries)
      ? snapshot.sessionEntries.map(([key]) => key)
      : null,
    hasCurrentContract: typeof snapshot?.localCurrentContract === "string",
    currentContractLength: typeof snapshot?.localCurrentContract === "string"
      ? snapshot.localCurrentContract.length
      : 0,
  });
  return snapshot;
}

async function resolveSourceMasarTabWithSnapshot(tabs) {
  const orderedTabs = rankSourceMasarTabs(tabs);
  let fallback = null;
  for (const tab of orderedTabs) {
    try {
      const snapshot = await captureMasarTabSnapshot(tab.id);
      if (!snapshot) {
        continue;
      }
      const context = extractMasarContextFromSnapshot(snapshot);
      if (!fallback) {
        fallback = { tab, snapshot, context };
      }
      if (context.hasContract && context.entityId) {
        return { tab, snapshot, context };
      }
    } catch (error) {
      logError("[details experiment] failed to inspect source tab", {
        tabId: tab.id,
        message: error?.message || String(error),
      });
    }
  }
  return fallback;
}

async function applyMasarTabSnapshot(tabId, snapshot) {
  if (!snapshot) {
    return false;
  }
  log("[details experiment] applyMasarTabSnapshot start", {
    tabId,
    sessionKeyCount: Array.isArray(snapshot.sessionEntries) ? snapshot.sessionEntries.length : 0,
    hasCurrentContract: typeof snapshot.localCurrentContract === "string",
  });
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    args: [snapshot],
    func: (capturedSnapshot) => {
      if (!capturedSnapshot || !Array.isArray(capturedSnapshot.sessionEntries)) {
        return false;
      }
      sessionStorage.clear();
      for (const [key, value] of capturedSnapshot.sessionEntries) {
        sessionStorage.setItem(key, value);
      }
      if (typeof capturedSnapshot.localCurrentContract === "string") {
        localStorage.setItem("currentContract", capturedSnapshot.localCurrentContract);
      }
      return true;
    },
  });
  const applied = results?.[0]?.result === true;
  log("[details experiment] applyMasarTabSnapshot complete", { tabId, applied });
  return applied;
}

async function markRecordMissing(uploadId) {
  if (!uploadId) {
    return false;
  }
  const record = await fetchRecordById(uploadId);
  await patchRecordStatus(uploadId, {
    status: "missing",
    masar_detail_id: record?.masar_detail_id || null,
    failure_reason_code: null,
    failure_reason_text: null,
    ...buildStoredSubmissionContext(record),
  });
  return true;
}

async function resolveMutamerDetailsOutcomeResult(outcome, uploadId) {
  if (outcome === "ready" || outcome === "unknown") {
    return { ok: true, mode: "clone" };
  }
  if (outcome === "mutamer-missing") {
    try {
      await markRecordMissing(uploadId);
      await Notifications.notify(
        Notifications.NOTIFICATION_TYPES.DETAILS_MISSING,
        S.DETAILS_RECORD_MISSING,
      );
    } catch (error) {
      logError("[details experiment] failed to patch missing mutamer status", {
        uploadId,
        message: error?.message || String(error),
      });
    }
    return { ok: false, errorCode: "mutamer-missing" };
  }
  if (outcome === "session-expired") {
    return { ok: false, errorCode: "mutamer-inaccessible" };
  }
  return { ok: false, errorCode: "mutamer-open-failed" };
}

async function openMutamerDetailsExperiment(clickUrl, uploadId = null, detailsContext = null) {
  log("[details experiment] start", { clickUrl });
  const masarTabs = await queryMasarTabs();
  const source = await resolveSourceMasarTabWithSnapshot(masarTabs);
  const sourceTab = source?.tab || null;
  const sourceSnapshot = source?.snapshot || null;
  const sourceContext = source?.context || null;
  const storedRecordContext = detailsContext || (uploadId ? await fetchRecordById(uploadId) : null);
  const detailsContextOverride = buildStoredDetailsContextOverride(storedRecordContext);
  log("[details experiment] selected source tab", sourceTab ? {
    id: sourceTab.id,
    windowId: sourceTab.windowId,
    url: sourceTab.url,
    active: sourceTab.active,
    hasContract: Boolean(sourceContext?.hasContract),
  } : null);
  if (!sourceTab) {
    log("[details experiment] no source tab available");
    await openMasarEntryTab({ active: true });
    return { ok: true, mode: "entry" };
  }
  if (!chrome.scripting?.executeScript) {
    log("[details experiment] scripting API unavailable");
    await navigateExistingMasarTab(sourceTab, clickUrl);
    return { ok: true, mode: "reuse" };
  }
  let newTab = null;
  try {
    const snapshot = applyDetailsContextOverrideToSnapshot(
      sourceSnapshot || await captureMasarTabSnapshot(sourceTab.id),
      detailsContextOverride,
    );
    log("[details experiment] captured snapshot summary", {
      sessionKeyCount: Array.isArray(snapshot?.sessionEntries) ? snapshot.sessionEntries.length : 0,
      hasCurrentContract: typeof snapshot?.localCurrentContract === "string",
    });
    if (!snapshot) {
      log("[details experiment] snapshot missing, falling back to reuse");
      await navigateExistingMasarTab(sourceTab, clickUrl);
      return { ok: true, mode: "reuse" };
    }
    newTab = await openMasarEntryTab({ active: false });
    if (!newTab || typeof newTab.id !== "number") {
      log("[details experiment] failed to create neutral tab");
      await navigateExistingMasarTab(sourceTab, clickUrl);
      return { ok: true, mode: "reuse" };
    }
    const applied = await applyMasarTabSnapshot(newTab.id, snapshot);
    if (!applied) {
      log("[details experiment] apply snapshot returned false, falling back to reuse");
      await closeTabQuietly(newTab.id, "snapshot-apply-failed");
      await navigateExistingMasarTab(sourceTab, clickUrl);
      return { ok: true, mode: "reuse" };
    }
    log("[details experiment] updating cloned tab to details URL", {
      tabId: newTab.id,
      clickUrl,
    });
    await chrome.tabs.update(newTab.id, { url: clickUrl, active: false });
    const readySnapshot = await waitForTabUrl(
      newTab.id,
      (snapshot) => typeof snapshot.url === "string" && snapshot.url.includes("/umrah/mutamer/mutamer-details/"),
      { attempts: 24, delayMs: 500 },
    );
    if (!readySnapshot || typeof readySnapshot.url !== "string" || !readySnapshot.url.includes("/umrah/mutamer/mutamer-details/")) {
      const failedProbe = await inspectMasarTabContent(newTab.id);
      const failedOutcome = classifyMutamerDetailsOutcome(readySnapshot, failedProbe);
      if (failedOutcome === "mutamer-missing" && readySnapshot?.status === "complete") {
        const failedOutcomeResult = await resolveMutamerDetailsOutcomeResult(failedOutcome, uploadId);
        log("[details experiment] preserving cloned tab for strong pre-ready missing outcome", {
          tabId: newTab.id,
          diagnostics: buildMutamerDetailsDiagnostics(readySnapshot, failedProbe),
        });
        await logClonedTabRuntimeState(newTab.id, "strong-pre-ready-missing");
        await activateTab(newTab.id, newTab.windowId);
        return failedOutcomeResult;
      }
      log("[details experiment] details route not reached before timeout; preserving cloned tab", {
        tabId: newTab.id,
        finalUrl: readySnapshot?.url || null,
        diagnostics: buildMutamerDetailsDiagnostics(readySnapshot, failedProbe),
      });
      await logClonedTabRuntimeState(newTab.id, "route-timeout-preserved");
      await activateTab(newTab.id, newTab.windowId);
      return { ok: true, mode: "clone-pending" };
    }
    log("[details experiment] navigated cloned tab", clickUrl);
    const renderResult = await waitForMutamerDetailsRender(newTab.id);
    const outcome = renderResult?.outcome || await handleMutamerDetailsOutcome(newTab.id);
    if (outcome === "ready" || outcome === "mutamer-missing" || outcome === "session-expired") {
      await activateTab(newTab.id, newTab.windowId);
    }
    void logFinalTabUrl(newTab.id);
    const outcomeResult = await resolveMutamerDetailsOutcomeResult(outcome, uploadId);
    if (!outcomeResult.ok) {
      log("[details experiment] preserving cloned tab for terminal render outcome", {
        tabId: newTab.id,
        outcome,
        diagnostics: buildMutamerDetailsDiagnostics(renderResult?.snapshot, renderResult?.probe),
      });
      await logClonedTabRuntimeState(newTab.id, `terminal-render:${outcome}`);
    }
    return outcomeResult;
  } catch (error) {
    logError("[details experiment] failed", {
      message: error?.message || String(error),
      stack: error?.stack || null,
    });
    await closeTabQuietly(newTab?.id, "exception-fallback-to-reuse");
    if (sourceTab) {
      await navigateExistingMasarTab(sourceTab, clickUrl);
      return { ok: true, mode: "reuse" };
    }
    await openMasarEntryTab({ active: true });
    return { ok: true, mode: "entry" };
  }
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

function resolveMasarRequestContext(batchContext, storedContext) {
  if (batchContext && typeof batchContext === "object" && batchContext.entity_id) {
    return {
      entity_id: batchContext.entity_id || null,
      entity_type_id: batchContext.entity_type_id || null,
      contract_id: batchContext.contract_id || null,
      auth_token: batchContext.auth_token || null,
    };
  }
  return {
    entity_id: storedContext?.masar_entity_id || null,
    entity_type_id: storedContext?.masar_entity_type_id || null,
    contract_id: storedContext?.masar_contract_id || null,
    auth_token: storedContext?.masar_auth_token || null,
  };
}

async function getMasarRequestContext({ preferBatch = false, override = null } = {}) {
  if (override) {
    return resolveMasarRequestContext(override, null);
  }
  const stored = await getMasarEntityHeaders();
  if (!preferBatch) {
    return resolveMasarRequestContext(null, stored);
  }
  const session = await sessionGet(["submission_batch_context"]);
  return resolveMasarRequestContext(session.submission_batch_context || null, stored);
}

// Build custom entity headers — do NOT include Cookie.
// The browser sends cookies automatically via credentials:'include' for
// requests that match host_permissions. Setting Cookie manually is a
// forbidden-header no-op in the Fetch API.
async function buildMasarHeaders(contextOverride = null) {
  const stored = await getMasarRequestContext({ override: contextOverride });
  const headers = {
    activeentityid: stored.entity_id || "",
    activeentitytypeid: stored.entity_type_id || "",
    contractid: stored.contract_id || "",
    "entity-id": stored.entity_id || "",
    "Content-Type": "application/json",
    accept: "application/json, text/plain, */*",
    "accept-language": "en",
  };
  if (stored.auth_token) {
    headers["Authorization"] = normalizeMasarAuthorizationHeader(stored.auth_token);
  }
  return headers;
}

// ─── Masar fetch helpers ──────────────────────────────────────────────────────
// Direct fetch from service worker — same approach that was working before.

async function masarFetch(url, options = {}, contextOverride = null) {
  const headers = await buildMasarHeaders(contextOverride);
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
async function masarFetchMultipart(url, formData, contextOverride = null) {
  const stored = await getMasarRequestContext({ override: contextOverride });
  log("masarFetchMultipart —", url, "entityId:", stored.entity_id, "contractId:", stored.contract_id, "hasAuth:", !!stored.auth_token);
  const headers = {
    activeentityid: stored.entity_id || "",
    activeentitytypeid: stored.entity_type_id || "",
    contractid: stored.contract_id || "",
    "entity-id": stored.entity_id || "",
    accept: "application/json, text/plain, */*",
    "accept-language": "en",
  };
  if (stored.auth_token) headers["Authorization"] = normalizeMasarAuthorizationHeader(stored.auth_token);
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers,
    body: formData,
  });
  log(`masarFetchMultipart ← ${res.status}`);
  return res;
}

function hasValidSessionSyncSignal(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return false;
  }
  const entityId = typeof snapshot.entityId === "string" ? snapshot.entityId.trim() : "";
  const jwt = typeof snapshot.jwt === "string" ? snapshot.jwt.trim() : "";
  return Boolean(entityId || jwt);
}

// Read all session values directly from the open masar tab's storage.
// sessionStorage: pms-ac_En_Id (entityId), pms-ac_En_Type_Id (entityTypeId), pms-tk_session (JWT)
// localStorage:   currentContract.contractId
async function syncSessionFromMasar() {
  try {
    const tabs = await chrome.tabs.query({ url: ["https://masar.nusuk.sa/*", "https://*.nusuk.sa/*"] });
    if (tabs.length === 0) {
      log("syncSessionFromMasar — no open masar tab");
      return false;
    }
    let s = null;
    for (const tab of tabs) {
      try {
        const results = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
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
        const candidate = results?.[0]?.result || null;
        if (hasValidSessionSyncSignal(candidate)) {
          s = candidate;
          break;
        }
      } catch {
        // Try another nusuk tab.
      }
    }
    if (!s) return false;

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

    const update = {};
    if (s.entityId)           update.masar_entity_id            = s.entityId;
    if (s.entityTypeId)       update.masar_entity_type_id       = s.entityTypeId;
    // Contract selection is user-controlled and should not auto-switch.
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
    return true;
  } catch (err) {
    // "Frame with ID 0 is showing error page" — masar tab is closed or on an error page.
    // Non-fatal: webRequest-captured values remain in storage and are used instead.
    if (err.message?.includes("error page") || err.message?.includes("Cannot access")) {
      log("syncSessionFromMasar — tab unavailable:", err.message);
    } else {
      logError("syncSessionFromMasar — error:", err.message);
    }
    return false;
  }
}

// Sync session data from the open masar tab into chrome.storage.local.
// Returns { ok: true } always — errors are non-fatal.
async function syncSession() {
  try {
    const synced = await syncSessionFromMasar();
    chrome.storage.local.set({
      masar_last_synced: Date.now(),
      ...(synced ? { session_expired: false, submit_auth_required: null } : {}),
    });
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
  const activeUiContext = await ContextChange.getActiveUiContext();
  const hasCurrentContext = Boolean(activeUiContext.entity_id || activeUiContext.contract_id);
  if (!hasCurrentContext) {
    await handleStableContextChange(context);
    return;
  }
  if (debouncedContextChecker) {
    debouncedContextChecker(context);
  }
}

async function handleStableContextChange(context) {
  const activeUiContext = await ContextChange.getActiveUiContext();
  const change = ContextChange.classifyObservedContextChange(activeUiContext, context);
  if (change === "entity_changed_observed" || !activeUiContext.entity_id) {
    let contracts = [];
    try {
      const nextHeaders = ContextChange.buildLegacyStoragePatch({
        ...activeUiContext,
        entity_id: context.entity_id || null,
        entity_type_id: context.entity_type_id || null,
        auth_token: context.auth_token || activeUiContext.auth_token || null,
        user_name: context.user_name || activeUiContext.user_name || null,
      });
      await localSet(nextHeaders);
      contracts = await fetchContracts();
    } catch (error) {
      logError("handleStableContextChange — failed to refresh contracts after entity change:", error.message);
    }
    const nextContext = ContextChange.buildObservedEntityChangeContext(activeUiContext, context, contracts);
    await ContextChange.setActiveUiContext(nextContext);
    await updateBadgeState();
    await Notifications.notify(Notifications.NOTIFICATION_TYPES.CONTEXT_CHANGE, S.CTX_CHANGED_ENTITY);
    return;
  }
  await ContextChange.setActiveUiContext({
    ...activeUiContext,
    entity_id: context.entity_id || activeUiContext.entity_id,
    entity_type_id: context.entity_type_id || activeUiContext.entity_type_id,
    auth_token: context.auth_token || activeUiContext.auth_token,
    user_name: context.user_name || activeUiContext.user_name,
  });
}

async function fetchGroups(contractId = null) {
  log("fetchGroups — calling GetGroupList");
  const contextOverride = contractId
    ? {
        ...(await getMasarRequestContext()),
        contract_id: contractId,
      }
    : null;
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
    },
    contextOverride,
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

async function fetchRecordPage(section, limit, offset) {
  const response = await apiFetch(
    `/records?section=${encodeURIComponent(section)}&limit=${limit}&offset=${offset}`,
  );
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
  return { ok: true, data: await response.json() };
}

async function fetchRecordCounts() {
  const response = await apiFetch("/records/counts");
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
  return { ok: true, data: await response.json() };
}

async function fetchSubmitEligibleIds(limit, offset) {
  const response = await apiFetch(
    `/records/ids?section=pending&limit=${limit}&offset=${offset}`,
  );
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
  return { ok: true, data: await response.json() };
}

async function fetchRecordById(uploadId) {
  const response = await apiFetch(`/records/${uploadId}`);
  if (!response.ok) {
    if (response.status === 401) {
      await localSet({ session_expired: true });
      await updateBadgeState({ failedCount: 0 });
      throw taggedError("backend-auth", `record ${response.status}`);
    }
    if (response.status === 404) {
      return null;
    }
    throw taggedError(null, `record ${response.status}`);
  }
  await localSet({ session_expired: false });
  return response.json();
}

function shouldSubmitRecord(record) {
  return record?.upload_status === "processed"
    && (!record?.masar_status || record.masar_status === "failed" || record.masar_status === "missing");
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

async function getCurrentSubmissionContext() {
  const stored = await localGet([
    "masar_entity_id",
    "masar_entity_type_id",
    "masar_user_name",
    "masar_contract_id",
    "masar_contract_number",
    "masar_contract_status_name",
    "masar_contract_name_ar",
    "masar_contract_name_en",
    "masar_group_id",
    "masar_group_name",
    "masar_group_number",
    "masar_auth_token",
  ]);
  return {
    submission_entity_id: stored.masar_entity_id || null,
    submission_entity_type_id: stored.masar_entity_type_id || null,
    submission_entity_name: stored.masar_user_name || null,
    submission_contract_id: stored.masar_contract_id || null,
    submission_contract_name: stored.masar_contract_name_ar || stored.masar_contract_name_en || null,
    submission_contract_name_ar: stored.masar_contract_name_ar || null,
    submission_contract_name_en: stored.masar_contract_name_en || null,
    submission_contract_number: stored.masar_contract_number || null,
    submission_contract_status: stored.masar_contract_status_name === "Active" ? true : null,
    submission_uo_subscription_status_id: 1,
    submission_group_id: stored.masar_group_id || null,
    submission_group_name: stored.masar_group_name || null,
    submission_group_number: stored.masar_group_number || null,
    auth_token: stored.masar_auth_token || null,
  };
}

function buildStoredSubmissionContext(record) {
  return {
    submission_entity_id: record?.submission_entity_id || null,
    submission_entity_type_id: record?.submission_entity_type_id || null,
    submission_entity_name: record?.submission_entity_name || null,
    submission_contract_id: record?.submission_contract_id || null,
    submission_contract_name: record?.submission_contract_name || null,
    submission_contract_name_ar: record?.submission_contract_name_ar || null,
    submission_contract_name_en: record?.submission_contract_name_en || null,
    submission_contract_number: record?.submission_contract_number || null,
    submission_contract_status:
      typeof record?.submission_contract_status === "boolean" ? record.submission_contract_status : null,
    submission_uo_subscription_status_id:
      typeof record?.submission_uo_subscription_status_id === "number"
        ? record.submission_uo_subscription_status_id
        : null,
    submission_group_id: record?.submission_group_id || null,
    submission_group_name: record?.submission_group_name || null,
    submission_group_number: record?.submission_group_number || null,
  };
}

function buildSubmissionBatchContext(submissionContext) {
  return {
    entity_id: submissionContext?.submission_entity_id || null,
    entity_type_id: submissionContext?.submission_entity_type_id || null,
    contract_id: submissionContext?.submission_contract_id || null,
    contract_name: submissionContext?.submission_contract_name || null,
    group_id: submissionContext?.submission_group_id || null,
    group_name: submissionContext?.submission_group_name || null,
    group_number: submissionContext?.submission_group_number || null,
    auth_token: submissionContext?.auth_token || null,
    started_at: Date.now(),
  };
}

async function buildRecordLookup(uploadIds) {
  const lookup = new Map();
  for (const uploadId of uploadIds) {
    const record = await fetchRecordById(uploadId);
    if (record?.upload_id === uploadId) {
      lookup.set(uploadId, record);
    }
  }
  return lookup;
}

async function clearSubmissionBatch() {
  await sessionSet({
    submission_batch: [],
    active_submit_id: null,
    last_submit_result: null,
    submission_state: ContextChange.SUBMISSION_STATES.IDLE,
  });
  await ContextChange.clearSubmissionBatchContext();
}

async function ensureSubmissionSessionConsistency() {
  if (_isDrainingSubmissions) {
    return;
  }
  const session = await sessionGet(["submission_batch", "active_submit_id"]);
  const batch = Array.isArray(session.submission_batch) ? session.submission_batch : [];
  if (batch.length > 0 || session.active_submit_id) {
    await clearSubmissionBatch();
  }
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

function buildPassportImageUpload(record, imageBytes) {
  const mimeType = typeof record?.mime_type === "string" && record.mime_type.trim()
    ? record.mime_type.trim()
    : "image/jpeg";
  const fileName = typeof record?.filename === "string" && record.filename.trim()
    ? record.filename.trim()
    : "passport.jpg";
  return {
    fileName,
    mimeType,
    blob: new Blob([imageBytes], { type: mimeType }),
  };
}

function buildFailureReason(failureKind, fallbackMessage = null) {
  if (failureKind === "scan-image-unclear") {
    return {
      code: "scan-image-unclear",
      text: "Passport image is not clear",
    };
  }
  if (failureKind === "contract-missing") {
    return {
      code: "contract-missing",
      text: "No contract sent in request",
    };
  }
  if (failureKind === "contract-inactive") {
    return {
      code: "contract-inactive",
      text: "No Active Contract",
    };
  }
  if (!fallbackMessage) {
    return { code: null, text: null };
  }
  return {
    code: "unknown",
    text: fallbackMessage,
  };
}

function classifyScanPassportFailure(traceError, requestContext) {
  const normalized = typeof traceError === "string" ? traceError.trim().toLowerCase() : "";
  if (normalized.includes("passport image is not clear")) {
    return "scan-image-unclear";
  }
  if (normalized.includes("no active contract")) {
    return requestContext?.contract_id ? "contract-inactive" : "contract-missing";
  }
  return null;
}

function canRotatePassportImage() {
  return typeof createImageBitmap === "function" && typeof OffscreenCanvas === "function";
}

async function rotateImageBlob(blob, degrees) {
  if (
    !canRotatePassportImage()
    || !blob
    || !degrees
  ) {
    return blob;
  }
  const bitmap = await createImageBitmap(blob);
  try {
    const normalized = ((degrees % 360) + 360) % 360;
    if (normalized === 0) {
      return blob;
    }
    const swapSides = normalized === 90 || normalized === 270;
    const canvas = new OffscreenCanvas(
      swapSides ? bitmap.height : bitmap.width,
      swapSides ? bitmap.width : bitmap.height,
    );
    const context = canvas.getContext("2d");
    if (!context) {
      return blob;
    }
    context.translate(canvas.width / 2, canvas.height / 2);
    context.rotate((normalized * Math.PI) / 180);
    context.drawImage(bitmap, -bitmap.width / 2, -bitmap.height / 2);
    return canvas.convertToBlob({ type: blob.type || "image/jpeg" });
  } finally {
    if (typeof bitmap.close === "function") {
      bitmap.close();
    }
  }
}

async function scanPassportWithFallback(imageUpload, requestContext) {
  const rotations = canRotatePassportImage() ? [0, 90, -90, 180] : [0];
  let lastError = null;
  for (const rotation of rotations) {
    const scanBlob =
      rotation === 0 ? imageUpload.blob : await rotateImageBlob(imageUpload.blob, rotation);
    const formData = new FormData();
    formData.append("passportImage", scanBlob, imageUpload.fileName);
    const response = await masarFetchMultipart(
      "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/ScanPassport",
      formData,
      requestContext,
    );
    log("submitToMasar [1/6] — status:", response.status, "rotation:", rotation);
    if (!response.ok) {
      let payload = null;
      let errorBody = null;
      try {
        payload = await response.json();
      } catch {
        errorBody = await response.text();
      }
      const traceError =
        payload?.traceError
        || payload?.TraceError
        || payload?.traceErrorStacktrace
        || payload?.responseDesc
        || errorBody
        || null;
      const failureKind = classifyScanPassportFailure(traceError, requestContext);
      if (failureKind === "scan-image-unclear" && rotation !== rotations[rotations.length - 1]) {
        log("submitToMasar [1/6] — retrying ScanPassport with rotation", { rotation, traceError });
        lastError = taggedError(failureKind, S.ERR_SCAN_IMAGE_UNCLEAR, {
          failureReason: buildFailureReason(failureKind, traceError),
        });
        continue;
      }
      if (failureKind) {
        throw taggedError(
          failureKind,
          failureKind === "scan-image-unclear"
            ? S.ERR_SCAN_IMAGE_UNCLEAR
            : S.ERR_CONTRACT_NOT_ACTIVE,
          { failureReason: buildFailureReason(failureKind, traceError) },
        );
      }
      logError("submitToMasar [1/6] — error body:", traceError || errorBody || payload);
      throw taggedError(
        response.status === 401 ? "masar-auth" : null,
        S.ERR_SCAN_PASSPORT(response.status),
        { failureReason: buildFailureReason(null, traceError || errorBody || null) },
      );
    }

    const payload = await response.json();
    if (!payload.response || !payload.response.data) {
      const traceError =
        payload.traceError
        || payload.TraceError
        || payload.traceErrorStacktrace
        || payload.responseDesc
        || "unknown";
      const failureKind = classifyScanPassportFailure(traceError, requestContext);
      if (failureKind === "scan-image-unclear" && rotation !== rotations[rotations.length - 1]) {
        log("submitToMasar [1/6] — retrying ScanPassport envelope with rotation", { rotation, traceError });
        lastError = taggedError(failureKind, S.ERR_SCAN_IMAGE_UNCLEAR, {
          failureReason: buildFailureReason(failureKind, traceError),
        });
        continue;
      }
      if (failureKind) {
        throw taggedError(
          failureKind,
          failureKind === "scan-image-unclear"
            ? S.ERR_SCAN_IMAGE_UNCLEAR
            : S.ERR_CONTRACT_NOT_ACTIVE,
          { failureReason: buildFailureReason(failureKind, traceError) },
        );
      }
      logError("submitToMasar [1/6] — ScanPassport returned no data. traceError:", traceError);
      throw taggedError(null, S.ERR_SCAN_NO_DATA, {
        failureReason: buildFailureReason(null, traceError),
      });
    }
    if (rotation !== 0) {
      log("submitToMasar [1/6] — ScanPassport succeeded after rotation", { rotation });
    }
    return payload.response.data;
  }
  if (lastError) {
    throw lastError;
  }
  throw taggedError(null, S.ERR_SCAN_NO_DATA);
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

async function submitToMasar(record, requestContext) {
  if (!requestContext?.contract_id) {
    throw taggedError("contract-missing", S.CONTRACT_ACTION_REQUIRED, {
      failureReason: buildFailureReason("contract-missing"),
    });
  }
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

  const imageBytes = await fetchImageBytes(record.upload_id);
  const imageUpload = buildPassportImageUpload(record, imageBytes);
  log("submitToMasar — image upload metadata:", {
    fileName: imageUpload.fileName,
    mimeType: imageUpload.mimeType,
    byteLength: imageBytes.byteLength,
  });

  // ── Step 1: ScanPassport ──────────────────────────────────────────────────
  log("submitToMasar [1/6] — ScanPassport");
  const step1Json = { response: { data: await scanPassportWithFallback(imageUpload, requestContext) } };
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
    { method: "POST", body: JSON.stringify(step2Body) },
    requestContext,
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
    { method: "POST", body: "{}" },
    requestContext,
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
  fd4.append("file", imageUpload.blob, imageUpload.fileName);
  let step4Res;
  for (let attempt = 0; attempt < 3; attempt++) {
    step4Res = await masarFetchMultipart(
      "https://masar.nusuk.sa/umrah/common_apis/api/Attachment/Upload",
      fd4,
      requestContext,
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
    { method: "POST", body: JSON.stringify(step5Body) },
    requestContext,
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
    { method: "POST", body: JSON.stringify(step6Body) },
    requestContext,
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
      requestContext,
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

function getContractState(contractOrEndDate) {
  const contract =
    contractOrEndDate && typeof contractOrEndDate === "object"
      ? contractOrEndDate
      : null;
  const contractEndDate = contract ? contract.contractEndDate : contractOrEndDate;
  const contractStatusId =
    contract && contract.contractStatus && typeof contract.contractStatus.id !== "undefined"
      ? Number(contract.contractStatus.id)
      : null;
  if (contractStatusId !== null && contractStatusId !== 0) {
    return "inactive";
  }
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

function buildContractSnapshotUpdate(contracts, selectedContractId) {
  const selected = (Array.isArray(contracts) ? contracts : []).find(
    (contract) => String(contract.contractId) === String(selectedContractId),
  );
  if (!selected) {
    return {
      masar_contract_id: "",
      masar_contract_name_en: "",
      masar_contract_name_ar: "",
      masar_contract_number: "",
      masar_contract_end_date: "",
      masar_contract_status_name: "",
      masar_contract_state: "unknown",
    };
  }
  return {
    masar_contract_id: String(selected.contractId),
    masar_contract_name_en: selected.companyNameEn || "",
    masar_contract_name_ar: selected.companyNameAr || "",
    masar_contract_number: selected.contractNumber || "",
    masar_contract_end_date: selected.contractEndDate || "",
    masar_contract_status_name: selected.contractStatus?.name || "",
    masar_contract_state: getContractState(selected),
  };
}

function shouldPersistContractSnapshot(currentValues, nextValues) {
  const keys = [
    "masar_contract_id",
    "masar_contract_name_en",
    "masar_contract_name_ar",
    "masar_contract_number",
    "masar_contract_end_date",
    "masar_contract_status_name",
    "masar_contract_state",
  ];
  return keys.some((key) => (currentValues?.[key] || "") !== (nextValues?.[key] || ""));
}

async function storeContractSnapshot(contracts) {
  if (!Array.isArray(contracts)) {
    return;
  }
  const stored = await localGet([
    "masar_contract_id",
    "masar_contract_name_en",
    "masar_contract_name_ar",
    "masar_contract_number",
    "masar_contract_end_date",
    "masar_contract_status_name",
    "masar_contract_state",
  ]);
  const nextSnapshot = buildContractSnapshotUpdate(contracts, stored.masar_contract_id);
  if (!shouldPersistContractSnapshot(stored, nextSnapshot)) {
    return;
  }
  await localSet(nextSnapshot);
}

async function processRecordSubmission(record, submissionContext, batchRequestContext) {
  try {
    const { mutamerId, scanResult, masarDetailId } = await submitToMasar(record, batchRequestContext);
    await patchRecordStatus(record.upload_id, {
      status: "submitted",
      masar_mutamer_id: String(mutamerId),
      masar_scan_result: scanResult,
      masar_detail_id: masarDetailId ? String(masarDetailId) : null,
      failure_reason_code: null,
      failure_reason_text: null,
      ...submissionContext,
    });
    await localSet({ session_expired: false, submit_auth_required: null });
    return {
      ok: true,
      uploadId: record.upload_id,
      status: "submitted",
      mutamerId,
      masarDetailId,
      ...submissionContext,
    };
  } catch (error) {
    logError("processRecordSubmission — failed:", error.message);
    const failureReason = error.failureReason || buildFailureReason(error.failureKind || null, error.message || null);
    if (error.failureKind === "backend-auth" || error.failureKind === "masar-auth") {
      await localSet({ session_expired: true, submit_auth_required: error.failureKind });
      await Notifications.notify(Notifications.NOTIFICATION_TYPES.SESSION_EXPIRED, S.NOTIF_SESSION_EXPIRED);
    }
    if (error.failureKind === "contract-inactive" || error.failureKind === "contract-missing") {
      try {
        const contracts = await fetchContracts();
        await storeContractSnapshot(contracts);
      } catch (refreshError) {
        logError("processRecordSubmission — failed to refresh contracts:", refreshError.message);
      }
    }
    try {
      await patchRecordStatus(record.upload_id, {
        status: "failed",
        masar_mutamer_id: null,
        masar_scan_result: null,
        masar_detail_id: null,
        failure_reason_code: failureReason.code,
        failure_reason_text: failureReason.text,
      });
    } catch (patchError) {
      logError("processRecordSubmission — failed to patch failed status:", patchError.message);
    }
    return {
      ok: false,
      uploadId: record.upload_id,
      status: "failed",
      error: error.message,
      failureKind: error.failureKind || null,
      failure_reason_code: failureReason.code,
      failure_reason_text: failureReason.text,
    };
  }
}

function shouldStopBatchAfterResult(result) {
  return result?.ok === false && (
    result.failureKind === "backend-auth"
    || result.failureKind === "masar-auth"
    || result.failureKind === "contract-missing"
    || result.failureKind === "contract-inactive"
  );
}

async function drainSubmissionBatch(uploadIds, { notifyComplete = true } = {}) {
  _isDrainingSubmissions = true;
  const uniqueIds = [...new Set(uploadIds)];
  try {
    await localSet({ submit_auth_required: null });
    const submissionContext = await getCurrentSubmissionContext();
    const batchRequestContext = buildSubmissionBatchContext(submissionContext);
    await ContextChange.setSubmissionBatchContext(batchRequestContext);
    await sessionSet({
      submission_batch: uniqueIds,
      active_submit_id: null,
      submission_state:
        uniqueIds.length > 1 ? ContextChange.SUBMISSION_STATES.QUEUED_MORE : ContextChange.SUBMISSION_STATES.IDLE,
    });
    const recordsLookup = await buildRecordLookup(uniqueIds);

    let processedCount = 0;
    let terminalFailure = null;
    for (const uploadId of uniqueIds) {
      const record = recordsLookup.get(uploadId) || null;
      if (!record || !shouldSubmitRecord(record)) {
        await removeFromBatch(uploadId);
        continue;
      }

      await sessionSet({ active_submit_id: uploadId });
      await ContextChange.setSubmissionState(ContextChange.SUBMISSION_STATES.SUBMITTING_CURRENT);
      const result = await processRecordSubmission(record, submissionContext, batchRequestContext);
      processedCount += 1;
      await sessionSet({
        last_submit_result: {
          upload_id: uploadId,
          status: result?.status || (result?.ok ? "submitted" : "failed"),
          masar_detail_id: result?.masarDetailId ? String(result.masarDetailId) : null,
          submission_entity_id: result?.submission_entity_id || null,
          submission_entity_type_id: result?.submission_entity_type_id || null,
          submission_entity_name: result?.submission_entity_name || null,
          submission_contract_id: result?.submission_contract_id || null,
          submission_contract_name: result?.submission_contract_name || null,
          submission_contract_name_ar: result?.submission_contract_name_ar || null,
          submission_contract_name_en: result?.submission_contract_name_en || null,
          submission_contract_number: result?.submission_contract_number || null,
          submission_contract_status:
            typeof result?.submission_contract_status === "boolean"
              ? result.submission_contract_status
              : null,
          submission_uo_subscription_status_id:
            typeof result?.submission_uo_subscription_status_id === "number"
              ? result.submission_uo_subscription_status_id
              : null,
          submission_group_id: result?.submission_group_id || null,
          submission_group_name: result?.submission_group_name || null,
          submission_group_number: result?.submission_group_number || null,
          failure_reason_code: result?.failure_reason_code || null,
          failure_reason_text: result?.failure_reason_text || null,
          at: Date.now(),
        },
      });

      const remaining = await removeFromBatch(uploadId);
      await sessionSet({ active_submit_id: null });
      if (shouldStopBatchAfterResult(result)) {
        terminalFailure = result;
        break;
      }
      if (remaining.length > 0) {
        await ContextChange.setSubmissionState(ContextChange.SUBMISSION_STATES.QUEUED_MORE);
      }
    }

    const tail = await sessionGet(["submission_batch"]);
    if ((tail.submission_batch || []).length > 0) {
      await clearSubmissionBatch();
    } else {
      await ContextChange.setSubmissionState(ContextChange.SUBMISSION_STATES.IDLE);
      await ContextChange.clearSubmissionBatchContext();
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
  } finally {
    _isDrainingSubmissions = false;
  }
}

async function handleMessage(msg) {
  log("handleMessage — type:", msg.type);
  if (msg.type === "POPUP_LOG") {
    log("[popup]", msg.scope || "popup", ...(Array.isArray(msg.args) ? msg.args : []));
    return { ok: true };
  }
  if (msg.type === "OPEN_MUTAMER_DETAILS_EXPERIMENT") {
    return openMutamerDetailsExperiment(msg.clickUrl, msg.uploadId || null, msg.detailsContext || null);
  }
  await ensureSubmissionSessionConsistency();

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
      const cached = await localGet(["masar_groups_cache", "masar_contract_id"]);
      if (!msg.contractId && cached.masar_groups_cache) {
        return { ok: true, data: cached.masar_groups_cache };
      }
      return { ok: true, data: await fetchGroups(msg.contractId || cached.masar_contract_id || null) };
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

  if (msg.type === "FETCH_RECORD_PAGE") {
    return fetchRecordPage(msg.section || "pending", msg.limit || 50, msg.offset || 0);
  }

  if (msg.type === "FETCH_RECORD_COUNTS") {
    return fetchRecordCounts();
  }

  if (msg.type === "FETCH_SUBMIT_ELIGIBLE_IDS") {
    return fetchSubmitEligibleIds(msg.limit || 100, msg.offset || 0);
  }

  if (msg.type === "SUBMIT_BATCH") {
    const uploadIds = Array.isArray(msg.uploadIds) ? msg.uploadIds : [];
    serialiseSubmit(() => drainSubmissionBatch(uploadIds)).catch((error) => {
      logError("SUBMIT_BATCH — unhandled submission failure:", error.message);
    });
    return { ok: true };
  }

  if (msg.type === "SUBMIT_RECORD") {
    const record = msg.record;
    if (!record?.upload_id) {
      return { ok: false, error: S.ERR_UNEXPECTED };
    }
    serialiseSubmit(() =>
      drainSubmissionBatch([record.upload_id], { notifyComplete: false }),
    ).catch((error) => {
      logError("SUBMIT_RECORD — unhandled submission failure:", error.message);
    });
    return { ok: true };
  }

  if (msg.type === "APPLY_CONTEXT_CHANGE") {
    await ContextChange.applyContextChange();
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
    buildPassportImageUpload,
    buildSubmissionBatchContext,
    buildStoredCurrentContractValue,
    buildStoredDetailsContextOverride,
    buildContractSnapshotUpdate,
    buildStoredSubmissionContext,
    classifyMutamerDetailsOutcome,
    countFailedRecords,
    extractMutamerDetailId,
    extractMasarContextFromSnapshot,
    fetchRecordCounts,
    fetchRecordPage,
    fetchSubmitEligibleIds,
    formatCookieDebugSummary,
    getCurrentSubmissionContext,
    handleMessage,
    hasValidSessionSyncSignal,
    markRecordMissing,
    normalizeMasarAuthorizationHeader,
    canRotatePassportImage,
    rankSourceMasarTabs,
    resolveMasarRequestContext,
    resolveMutamerDetailsOutcomeResult,
    selectSourceMasarTab,
    shouldPersistContractSnapshot,
    shouldStopBatchAfterResult,
    shouldSubmitRecord,
  };
}

if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
  startBackground();
}
