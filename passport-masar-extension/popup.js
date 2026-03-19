// ─── Utilities ────────────────────────────────────────────────────────────────

function $(id) { return document.getElementById(id); }

function showScreen(name) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.add("hidden"));
  $(`screen-${name}`).classList.remove("hidden");
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

function sendMsg(msg) {
  return new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
}

// ─── Name helpers ─────────────────────────────────────────────────────────────

function buildDisplayName(record) {
  if (record.core_result) {
    const r = record.core_result;
    const parts = [r.first_name_en, r.last_name_en].filter(Boolean);
    if (parts.length) return parts.join(" ");
  }
  return record.passport_number || `Record #${record.upload_id}`;
}

function buildNationality(record) {
  return record.core_result?.nationality || "";
}

// ─── Queue rendering ──────────────────────────────────────────────────────────

let pendingRecords = [];
let skippedIds = new Set();

function renderQueue() {
  const list = $("queue-list");
  list.innerHTML = "";

  const visible = pendingRecords.filter((r) => !skippedIds.has(r.upload_id));
  $("pending-count").textContent = `Pending (${visible.length})`;

  if (visible.length === 0) {
    list.innerHTML = '<div class="empty-state">&#10003; No more pending</div>';
    return;
  }

  visible.forEach((record) => {
    const item = document.createElement("div");
    item.className = "queue-item";
    item.dataset.id = record.upload_id;

    const name = buildDisplayName(record);
    const nat = buildNationality(record);
    const passNum = record.passport_number || "";

    item.innerHTML = `
      <div class="record-name">${name}</div>
      <div class="record-meta">${nat}${nat && passNum ? " · " : ""}${passNum ? "#" + passNum : ""}</div>
      <div class="record-actions">
        <button class="btn-submit">Submit</button>
        <button class="btn-skip secondary">Skip</button>
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

  btnSubmit.disabled = true;
  btnSkip.disabled = true;
  statusEl.className = "status-msg loading";
  statusEl.classList.remove("hidden");
  statusEl.textContent = "Submitting…";

  const res = await sendMsg({ type: "SUBMIT_RECORD", record });

  if (res && res.ok) {
    statusEl.className = "status-msg success";
    statusEl.textContent = "Submitted successfully";
    // Remove from list after a brief pause
    setTimeout(() => {
      pendingRecords = pendingRecords.filter((r) => r.upload_id !== record.upload_id);
      renderQueue();
    }, 1200);
  } else {
    const err = res?.error || "Unknown error";
    statusEl.className = "status-msg error";
    if (err.includes("401") || err.includes("403")) {
      statusEl.textContent = "Log into masar.nusuk.sa then retry";
    } else {
      statusEl.textContent = `Error: ${err}`;
    }
    btnSubmit.disabled = false;
    btnSkip.disabled = false;
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  const stored = await storageGet([
    "api_token",
    "api_base_url",
    "masar_entity_id",
    "masar_group_id",
    "agency_email",
    "agency_phone",
    "agency_phone_country_code",
  ]);

  // 1. No token → show setup
  if (!stored.api_token) {
    showScreen("setup");
    return;
  }

  // 2. No entity IDs captured yet → prompt to open masar
  if (!stored.masar_entity_id) {
    showScreen("activate");
    return;
  }

  // 3. Check masar session
  const sessionCheck = await sendMsg({ type: "CHECK_SESSION" });
  if (!sessionCheck || !sessionCheck.ok) {
    showScreen("session-expired");
    return;
  }

  // 4. No group selected → show group picker
  if (!stored.masar_group_id) {
    await loadGroupPicker();
    return;
  }

  // 5. Main queue
  await loadMainQueue(stored);
}

async function loadGroupPicker() {
  showScreen("group-select");
  const res = await sendMsg({ type: "FETCH_GROUPS" });
  const select = $("group-select");
  select.innerHTML = "";

  if (!res || !res.ok) {
    select.innerHTML = '<option value="">Failed to load groups</option>';
    return;
  }

  const groups = Array.isArray(res.data) ? res.data : (res.data?.data || res.data?.items || []);
  groups.forEach((g) => {
    const opt = document.createElement("option");
    opt.value = g.id || g.groupId;
    opt.textContent = g.name || g.groupName || opt.value;
    select.appendChild(opt);
  });
}

async function loadMainQueue() {
  showScreen("main");
  const res = await sendMsg({ type: "FETCH_PENDING" });

  if (!res || !res.ok) {
    $("queue-list").innerHTML = `<div class="status-msg error">Failed to load queue (${res?.status || "network error"})</div>`;
    return;
  }

  pendingRecords = res.data || [];
  renderQueue();
}

// ─── Event listeners ──────────────────────────────────────────────────────────

// Setup screen
$("btn-save-token").addEventListener("click", async () => {
  const token = $("api-token-input").value.trim();
  const baseUrl = $("api-base-url-input").value.trim().replace(/\/$/, "");
  if (!token || !baseUrl) return;
  await storageSet({ api_token: token, api_base_url: baseUrl });
  init();
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
  await storageSet({ masar_group_id: groupId });
  loadMainQueue();
});

// Settings button
$("btn-settings").addEventListener("click", async () => {
  const stored = await storageGet(["agency_email", "agency_phone", "agency_phone_country_code"]);
  $("settings-email").value = stored.agency_email || "";
  $("settings-phone-cc").value = stored.agency_phone_country_code || "966";
  $("settings-phone").value = stored.agency_phone || "";
  showScreen("settings");
});

$("btn-back").addEventListener("click", () => loadMainQueue());

$("btn-save-settings").addEventListener("click", async () => {
  await storageSet({
    agency_email: $("settings-email").value.trim(),
    agency_phone_country_code: $("settings-phone-cc").value.trim(),
    agency_phone: $("settings-phone").value.trim(),
  });
  loadMainQueue();
});

$("btn-change-group").addEventListener("click", async () => {
  await storageRemove(["masar_group_id"]);
  loadGroupPicker();
});

$("btn-reset-token").addEventListener("click", async () => {
  await storageRemove(["api_token", "api_base_url", "masar_group_id"]);
  showScreen("setup");
});

// ─── Boot ──────────────────────────────────────────────────────────────────────
init();
