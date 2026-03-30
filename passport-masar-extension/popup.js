// ─── Utilities ────────────────────────────────────────────────────────────────

function $(id) { return document.getElementById(id); }

function showScreen(name) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.add("hidden"));
  const el = $(`screen-${name}`);
  if (el) {
    el.classList.remove("hidden");
  } else {
    console.error("[masar-ext popup] showScreen: no element with id screen-" + name);
  }
}

function showError(msg) {
  $("error-detail").textContent = msg;
  showScreen("error");
}

function showSetupError(msg) {
  const el = $("setup-error");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
}

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}
function storageSet(data) {
  return new Promise((resolve) => chrome.storage.local.set(data, resolve));
}
function storageRemove(keys) {
  return new Promise((resolve) => chrome.storage.local.remove(keys, resolve));
}

// sendMsg with a 15-second timeout so popup never hangs blank.
function sendMsg(msg) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      console.error("[masar-ext popup] sendMsg timeout for", msg.type);
      resolve({ ok: false, error: S.ERR_TIMEOUT });
    }, 15000);
    chrome.runtime.sendMessage(msg, (resp) => {
      clearTimeout(timer);
      if (chrome.runtime.lastError) {
        console.error("[masar-ext popup] sendMsg error:", chrome.runtime.lastError.message);
        resolve({ ok: false, error: S.ERR_UNEXPECTED });
        return;
      }
      resolve(resp);
    });
  });
}

// ─── Name helpers ─────────────────────────────────────────────────────────────

function buildDisplayName(record) {
  const d = record.extraction_result?.data;
  if (d) {
    const givenTokens = Array.isArray(d.GivenNameTokensEn) ? d.GivenNameTokensEn : [];
    const given = givenTokens.join(" ");
    const parts = [given, d.SurnameEn].filter(Boolean);
    if (parts.length) return parts.join(" — ");
  }
  return record.passport_number || S.RECORD_FALLBACK(record.upload_id);
}

function buildNationality(record) {
  return record.extraction_result?.data?.CountryCode || "";
}

function reviewLabel(record) {
  if (record.review_status === "needs_review") return S.REVIEW_REQUIRED;
  if (record.review_status === "reviewed") return S.REVIEW_DONE;
  return S.REVIEW_AUTO;
}

// ─── Context panel ────────────────────────────────────────────────────────────

async function populateContextPanel() {
  const data = await storageGet([
    "masar_entity_id",
    "masar_user_name",
    "masar_contract_id",
    "masar_contract_number",
    "masar_contract_name_en",
    "masar_contract_end_date",
    "masar_contract_state",
    "masar_group_id",
    "masar_group_name",
    "masar_group_number",
    "masar_last_synced",
  ]);

  // Account row
  const entityParts = [data.masar_user_name, data.masar_entity_id ? `(${data.masar_entity_id})` : null].filter(Boolean);
  $("ctx-entity").textContent = entityParts.join(" ") || "—";

  // Contract row
  const contractParts = [
    data.masar_contract_number ? `#${data.masar_contract_number}` : null,
    data.masar_contract_name_en,
  ].filter(Boolean);
  $("ctx-contract").textContent = contractParts.join(" · ") || (data.masar_contract_id || "—");

  // Contract end date + state
  const state = data.masar_contract_state || "unknown";
  const endEl = $("ctx-contract-end");
  if (data.masar_contract_end_date) {
    const dateStr = data.masar_contract_end_date.slice(0, 10);
    const labels = { active: S.CONTRACT_ACTIVE, "expires-today": S.CONTRACT_EXPIRES_TODAY, expired: S.CONTRACT_EXPIRED, unknown: "" };
    const label = labels[state] || "";
    endEl.innerHTML = `<span class="status-dot ${state}"></span>${dateStr}${label ? ` · ${label}` : ""}`;
  } else {
    endEl.innerHTML = "—";
  }

  // Group row
  const groupParts = [data.masar_group_number, data.masar_group_name].filter(Boolean);
  $("ctx-group").textContent = groupParts.join(" · ") || (data.masar_group_id || "—");

  // Last synced
  if (data.masar_last_synced) {
    const ago = Math.round((Date.now() - data.masar_last_synced) / 1000);
    $("ctx-synced").textContent = ago < 60 ? S.CTX_SYNCED_NOW : S.CTX_SYNCED_AGO(Math.round(ago / 60));
  } else {
    $("ctx-synced").textContent = S.CTX_NOT_SYNCED;
  }

  // Show/hide banners based on contract state
  $("banner-contract-expired").classList.toggle("hidden", state !== "expired");
  $("banner-contract-expiring").classList.toggle("hidden", state !== "expires-today");
}

// ─── Queue rendering ──────────────────────────────────────────────────────────

let pendingRecords = [];
let skippedIds = new Set();

function renderQueue() {
  const list = $("queue-list");
  list.innerHTML = "";

  const visible = pendingRecords.filter((r) => !skippedIds.has(r.upload_id));
  $("pending-count").textContent = S.PENDING_COUNT(visible.length);

  if (visible.length === 0) {
    const emptyEl = document.createElement("div");
    emptyEl.className = "empty-state";
    emptyEl.textContent = S.QUEUE_EMPTY;
    list.appendChild(emptyEl);
    return;
  }

  visible.forEach((record) => {
    const item = document.createElement("div");
    item.className = "queue-item";
    item.dataset.id = record.upload_id;

    const name = buildDisplayName(record);
    const nat = buildNationality(record);
    const passNum = record.passport_number || "";
    const reviewText = reviewLabel(record);
    const reviewClass = record.review_status === "needs_review" ? "needs-review" : "ok";

    item.innerHTML = `
      <div class="record-name">${name}</div>
      <div class="record-meta">${nat}${nat && passNum ? " · " : ""}${passNum ? "#" + passNum : ""}</div>
      <div class="record-review ${reviewClass}">${reviewText}</div>
      <div class="record-actions">
        <button class="btn-submit">${S.BTN_SUBMIT}</button>
        <button class="btn-skip secondary">${S.BTN_SKIP}</button>
      </div>
      <div class="status-msg hidden"></div>
    `;

    item.querySelector(".btn-submit").addEventListener("click", () => submitRecord(record, item));
    item.querySelector(".btn-skip").addEventListener("click", () => {
      skippedIds.add(record.upload_id);
      renderQueue();
    });

    list.appendChild(item);
  });
}

async function submitRecord(record, item) {
  const btnSubmit = item.querySelector(".btn-submit");
  const btnSkip = item.querySelector(".btn-skip");
  const statusEl = item.querySelector(".status-msg");

  if (record.review_status === "needs_review") {
    const confirmed = window.confirm(S.REVIEW_CONFIRM);
    if (!confirmed) return;
    const reviewRes = await sendMsg({ type: "MARK_REVIEWED", uploadId: record.upload_id });
    if (!reviewRes || !reviewRes.ok) {
      statusEl.className = "status-msg error";
      statusEl.classList.remove("hidden");
      statusEl.textContent = S.REVIEW_UPDATE_FAILED(reviewRes?.status || reviewRes?.error || "?");
      return;
    }
    record.review_status = "reviewed";
  }

  btnSubmit.disabled = true;
  btnSkip.disabled = true;
  statusEl.className = "status-msg loading";
  statusEl.classList.remove("hidden");
  statusEl.textContent = S.SUBMITTING;

  const res = await sendMsg({ type: "SUBMIT_RECORD", record });

  // Always re-fetch from API — source of truth.
  // This handles the case where Chrome closes the message port during a long
  // retry wait and sendMsg returns null even though the submission succeeded.
  const freshRes = await sendMsg({ type: "FETCH_PENDING" });
  if (freshRes && freshRes.ok) {
    pendingRecords = freshRes.data;
  }

  if (res && res.ok) {
    statusEl.className = "status-msg success";
    statusEl.textContent = S.SUBMIT_SUCCESS;
    setTimeout(() => renderQueue(), 1200);
  } else {
    // Check if this record is actually gone from the API (succeeded despite lost port)
    const stillPending = pendingRecords.some((r) => r.upload_id === record.upload_id);
    if (!stillPending) {
      statusEl.className = "status-msg success";
      statusEl.textContent = S.SUBMIT_SUCCESS;
      setTimeout(() => renderQueue(), 1200);
      return;
    }
    const err = res?.error || "Unknown error";
    statusEl.className = "status-msg error";
    if (err.includes("401") || err.includes("session") || err.includes("login")) {
      statusEl.textContent = S.ERR_SESSION;
    } else {
      statusEl.textContent = S.ERR_GENERIC(err);
    }
    btnSubmit.disabled = false;
    btnSkip.disabled = false;
    renderQueue();
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  showScreen("loading");

  const stored = await storageGet([
    "api_token",
    "masar_entity_id",
    "masar_group_id",
    "masar_auth_token",
    "agency_email",
    "agency_phone",
    "agency_phone_country_code",
  ]);

  console.log("[masar-ext popup] init — stored:", {
    api_token: !!stored.api_token,
    masar_entity_id: stored.masar_entity_id,
    masar_auth_token: stored.masar_auth_token ? stored.masar_auth_token.slice(0, 20) + "..." : null,
    masar_group_id: stored.masar_group_id,
  });

  // 1. No token → show setup
  if (!stored.api_token) {
    showSetupError("");
    showScreen("setup");
    return;
  }

  // 2. No entity IDs captured yet → prompt to open masar
  if (!stored.masar_entity_id) {
    showScreen("activate");
    return;
  }

  // 3. Sync session data from open masar tab (best-effort, don't block on failure)
  const syncRes = await sendMsg({ type: "SYNC_SESSION" });
  console.log("[masar-ext popup] SYNC_SESSION:", syncRes);

  // 4. No group selected → show group picker
  if (!stored.masar_group_id) {
    // Re-read storage after sync in case group was captured
    const refreshed = await storageGet(["masar_group_id"]);
    if (!refreshed.masar_group_id) {
      await loadGroupPicker();
      return;
    }
  }

  // 5. Main queue
  await loadMainQueue();
}

async function loadGroupPicker() {
  showScreen("group-select");
  const res = await sendMsg({ type: "FETCH_GROUPS" });
  const select = $("group-select");
  select.innerHTML = "";

  console.log("[masar-ext popup] FETCH_GROUPS response:", JSON.stringify(res).slice(0, 500));

  if (!res || !res.ok) {
    select.innerHTML = `<option value="">${S.GROUP_LOAD_FAILED}</option>`;
    $("group-select-hint").classList.remove("hidden");
    return;
  }
  $("group-select-hint").classList.add("hidden");

  // Unwrap the masar envelope: { response: { data: { content: [...] } } }
  const groups = res.data?.response?.data?.content || [];

  console.log("[masar-ext popup] groups count:", groups.length, "first:", JSON.stringify(groups[0]).slice(0, 200));

  if (groups.length === 0) {
    select.innerHTML = `<option value="">${S.GROUP_NONE_FOUND}</option>`;
    $("group-select-hint").classList.remove("hidden");
    return;
  }
  $("group-select-hint").classList.add("hidden");

  groups.forEach((g) => {
    const opt = document.createElement("option");
    opt.value = g.id;
    opt.dataset.groupName = g.groupName || "";
    opt.dataset.groupNumber = g.groupNumber || "";
    const label = [g.groupNumber, g.groupName].filter(Boolean).join(" · ");
    opt.textContent = label || String(g.id);
    select.appendChild(opt);
  });
}

async function loadMainQueue() {
  showScreen("main");
  await populateContextPanel();

  const res = await sendMsg({ type: "FETCH_PENDING" });

  if (!res || !res.ok) {
    if (res?.status === 401) {
      showScreen("session-expired");
      return;
    }
    $("queue-list").innerHTML = `<div class="status-msg error">${S.QUEUE_LOAD_FAILED(res?.status || res?.error || "?")}</div>`;
    return;
  }

  pendingRecords = res.data || [];
  renderQueue();
}

// ─── Event listeners ──────────────────────────────────────────────────────────

// Setup screen
$("btn-save-token").addEventListener("click", async () => {
  const token = $("api-token-input").value.trim();
  const btn = $("btn-save-token");
  if (!token) return;
  showSetupError("");
  btn.disabled = true;
  try {
    const issued = await MasarAuth.exchangeTempToken({
      apiBaseUrl: API_BASE_URL,
      tempToken: token,
      fetchImpl: fetch,
    });
    await storageSet({
      api_token: issued.sessionToken,
    });
    $("api-token-input").value = "";
    await init();
  } catch (err) {
    showSetupError(S.SETUP_LOGIN_FAILED(err?.message || ""));
  } finally {
    btn.disabled = false;
  }
});

// Activate screen
$("btn-open-masar-activate").addEventListener("click", () => {
  sendMsg({ type: "OPEN_MASAR" });
});

// Session expired screen
$("btn-open-masar-expired").addEventListener("click", () => {
  sendMsg({ type: "OPEN_MASAR" });
});

// Group picker
$("btn-confirm-group").addEventListener("click", async () => {
  const select = $("group-select");
  const groupId = select.value;
  if (!groupId) return;
  const opt = select.options[select.selectedIndex];
  await storageSet({
    masar_group_id: groupId,
    masar_group_name: opt?.dataset.groupName || "",
    masar_group_number: opt?.dataset.groupNumber || "",
  });
  loadMainQueue();
});

// Persistent settings button (always visible in topbar)
$("btn-settings").addEventListener("click", async () => {
  const stored = await storageGet(["agency_email", "agency_phone", "agency_phone_country_code"]);
  $("settings-email").value = stored.agency_email || "";
  $("settings-phone-cc").value = stored.agency_phone_country_code || "966";
  $("settings-phone").value = stored.agency_phone || "";
  showScreen("settings");
});

$("btn-back").addEventListener("click", () => init());

$("btn-save-settings").addEventListener("click", async () => {
  await storageSet({
    agency_email: $("settings-email").value.trim(),
    agency_phone_country_code: $("settings-phone-cc").value.trim(),
    agency_phone: $("settings-phone").value.trim(),
  });
  init();
});

$("btn-change-group").addEventListener("click", async () => {
  await storageRemove(["masar_group_id", "masar_group_name", "masar_group_number"]);
  loadGroupPicker();
});

// Context panel refresh — re-sync from the open Masar tab then re-init
// so any context change (account switch, contract change) is picked up.
$("btn-refresh-context").addEventListener("click", async () => {
  $("ctx-synced").textContent = S.CTX_SYNCING;
  await sendMsg({ type: "SYNC_SESSION" });
  init();
});

$("btn-reset-token").addEventListener("click", async () => {
  await storageRemove(["api_token", "masar_group_id"]);
  showSetupError("");
  showScreen("setup");
});

// ─── Boot ──────────────────────────────────────────────────────────────────────
init().catch((err) => {
  console.error("[masar-ext popup] init failed:", err);
  showError(err.message || String(err));
});
