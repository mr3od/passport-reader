(function (root, factory) {
  const api = factory({
    Auth: root.MasarAuth || require("./auth.js"),
    ContractSelect: root.MasarContractSelect || require("./contract-select.js"),
    ContextChange: root.MasarContextChange || require("./context-change.js"),
    Failure: root.MasarPopupFailure || require("./popup-failure.js"),
    QueueFilter: root.MasarQueueFilter || require("./queue-filter.js"),
    Status: root.MasarStatus || require("./status.js"),
    Strings: root.MasarStrings || require("./strings.js"),
    apiBaseUrl: root.API_BASE_URL || "",
  });
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarPopup = api;
  if (typeof document !== "undefined" && typeof chrome !== "undefined") {
    api.bootstrap().catch((error) => {
      console.error("[masar-ext popup] bootstrap failed:", error);
    });
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function ({
  Auth,
  ContractSelect,
  ContextChange,
  Failure,
  QueueFilter,
  Status,
  Strings,
  apiBaseUrl,
}) {
  const state = {
    activeTab: "pending",
    hiddenContextBanner: false,
    pendingRecords: [],
    skippedIds: new Set(),
    sectionData: null,
    lastFetchedRecords: [],
    isWorkspaceLoading: false,
    hasQueuedWorkspaceReload: false,
    pendingReloadTimer: null,
    pendingReloadFetchRecords: false,
    pendingReloadRefreshContracts: false,
    contractsCache: null,
    contractsCacheAt: 0,
  };
  const CONTRACT_CACHE_TTL_MS = 30000;
  const WORKSPACE_LOCAL_REFRESH_KEYS = new Set([
    "masar_entity_id",
    "masar_user_name",
    "masar_contract_id",
    "session_expired",
    "submit_auth_required",
    "masar_contract_name_ar",
    "masar_contract_name_en",
    "masar_contract_state",
    "masar_group_id",
    "masar_group_name",
  ]);
  const WORKSPACE_SESSION_REFRESH_KEYS = new Set([
    "submission_batch",
    "active_submit_id",
    "last_submit_result",
  ]);

  function $(id, doc = document) {
    return doc.getElementById(id);
  }

  function getScreenTheme(name) {
    switch (name) {
      case "setup":
      case "group-select":
      case "settings":
        return { tone: "amber", surface: "editorial" };
      case "activate":
        return { tone: "green", surface: "editorial" };
      case "session-expired":
      case "error":
        return { tone: "red", surface: "editorial" };
      case "loading":
        return { tone: "olive", surface: "editorial" };
      case "main":
        return { tone: "olive", surface: "workspace" };
      default:
        return { tone: "amber", surface: "editorial" };
    }
  }

  function applyScreenTheme(name, doc = document) {
    const shell = $("popup-shell", doc);
    if (!shell) {
      return;
    }
    const theme = getScreenTheme(name);
    shell.dataset.screenTone = theme.tone;
    shell.dataset.screenSurface = theme.surface;
  }

  function showScreen(name, doc = document) {
    doc.querySelectorAll(".screen").forEach((element) => element.classList.add("hidden"));
    const screen = $(`screen-${name}`, doc);
    if (screen) {
      screen.classList.remove("hidden");
    }
    applyScreenTheme(name, doc);
  }

  function shouldRefreshWorkspaceForStorageChange({
    areaName,
    changes,
    isMainScreenVisible,
  }) {
    if (!isMainScreenVisible || !changes || typeof changes !== "object") {
      return false;
    }
    const refreshKeys =
      areaName === "local"
        ? WORKSPACE_LOCAL_REFRESH_KEYS
        : areaName === "session"
          ? WORKSPACE_SESSION_REFRESH_KEYS
          : null;
    if (!refreshKeys) {
      return false;
    }
    return Object.keys(changes).some((key) => refreshKeys.has(key));
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

  function sendMsg(message, { timeoutMs = 15000 } = {}) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => resolve({ ok: false, error: Strings.ERR_TIMEOUT }), timeoutMs);
      chrome.runtime.sendMessage(message, (response) => {
        clearTimeout(timer);
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(response);
      });
    });
  }

  function setStaticCopy(doc = document) {
    doc.title = Strings.TOPBAR_TITLE;
    $("topbar-title", doc).textContent = Strings.TOPBAR_TITLE;
    $("topbar-kicker", doc).textContent = Strings.TOPBAR_KICKER;
    $("help-support-link", doc).textContent = "؟";
    $("help-support-link", doc).title = Strings.HELP_LINK_LABEL;
    $("help-support-link", doc).ariaLabel = Strings.HELP_LINK_LABEL;
    $("help-support-link", doc).href = apiBaseUrl || "#";
    $("btn-settings", doc).textContent = "⚙";
    $("btn-settings", doc).title = Strings.ACTION_SETTINGS;
    $("btn-settings", doc).ariaLabel = Strings.ACTION_SETTINGS;
    $("loading-kicker", doc).textContent = Strings.LOADING_KICKER;
    $("loading-title", doc).textContent = Strings.LOADING;
    $("loading-subtitle", doc).textContent = Strings.LOADING_SUBTITLE;
    $("loading-text", doc).textContent = Strings.LOADING_HINT;
    $("error-kicker", doc).textContent = Strings.ERROR_KICKER;
    $("error-title", doc).textContent = Strings.ERROR_TITLE;
    $("error-subtitle", doc).textContent = Strings.ERROR_SUBTITLE;
    $("setup-kicker", doc).textContent = Strings.SETUP_KICKER;
    $("setup-title", doc).textContent = Strings.SETUP_TITLE;
    $("setup-subtitle", doc).textContent = Strings.SETUP_SUBTITLE;
    $("setup-token-label", doc).textContent = Strings.SETUP_TOKEN_LABEL;
    $("api-token-input", doc).placeholder = Strings.SETUP_TOKEN_PLACEHOLDER;
    $("btn-save-token", doc).textContent = Strings.SETUP_SAVE;
    $("setup-helper", doc).textContent = Strings.SETUP_HELP;
    $("activate-kicker", doc).textContent = Strings.ACTIVATE_KICKER;
    $("activate-title", doc).textContent = Strings.ACTIVATE_TITLE;
    $("activate-subtitle", doc).textContent = Strings.ACTIVATE_SUBTITLE;
    $("activate-message", doc).textContent = Strings.ACTIVATE_MESSAGE;
    $("btn-open-masar-activate", doc).textContent = Strings.OPEN_LOGIN;
    $("session-kicker", doc).textContent = Strings.SESSION_KICKER;
    $("session-title", doc).textContent = Strings.SESSION_EXPIRED;
    $("session-subtitle", doc).textContent = Strings.SESSION_SUBTITLE;
    $("btn-open-masar-expired", doc).textContent = Strings.OPEN_LOGIN;
    $("group-kicker", doc).textContent = Strings.GROUP_KICKER;
    $("group-title", doc).textContent = Strings.GROUP_TITLE;
    $("group-subtitle", doc).textContent = Strings.GROUP_SUBTITLE;
    $("group-select-label", doc).textContent = Strings.GROUP_SELECT_LABEL;
    $("group-select-hint", doc).textContent = Strings.GROUP_HINT;
    $("btn-confirm-group", doc).textContent = Strings.GROUP_CONFIRM;
    $("main-kicker", doc).textContent = Strings.MAIN_KICKER;
    $("main-title", doc).textContent = Strings.MAIN_TITLE;
    $("main-subtitle", doc).textContent = Strings.MAIN_SUBTITLE;
    $("workspace-summary-title", doc).textContent = Strings.MAIN_SUMMARY_TITLE;
    $("workspace-summary-subtitle", doc).textContent = Strings.MAIN_SUMMARY_SUBTITLE;
    $("home-office-label", doc).textContent = Strings.HOME_OFFICE_LABEL;
    $("home-contract-label", doc).textContent = Strings.HOME_CONTRACT_LABEL;
    $("home-group-label", doc).textContent = Strings.HOME_GROUP_LABEL;
    $("home-pending-label", doc).textContent = Strings.HOME_PENDING_LABEL;
    $("home-failed-label", doc).textContent = Strings.HOME_FAILED_LABEL;
    $("contract-select-label", doc).textContent = Strings.CONTRACT_SELECT_LABEL;
    $("btn-change-group", doc).textContent = Strings.GROUP_CHANGE;
    $("btn-refresh-context", doc).textContent = Strings.ACTION_REFRESH;
    $("tab-label-pending", doc).textContent = Strings.SECTION_PENDING;
    $("tab-label-in-progress", doc).textContent = Strings.SECTION_IN_PROGRESS;
    $("tab-label-submitted", doc).textContent = Strings.SECTION_SUBMITTED;
    $("tab-label-failed", doc).textContent = Strings.SECTION_FAILED;
    $("pending-title", doc).textContent = Strings.SECTION_PENDING;
    $("in-progress-title", doc).textContent = Strings.SECTION_IN_PROGRESS;
    $("submitted-title", doc).textContent = Strings.SECTION_SUBMITTED;
    $("failed-title", doc).textContent = Strings.SECTION_FAILED;
    $("submit-all-btn", doc).textContent = Strings.ACTION_SUBMIT_ALL;
    $("ctx-change-confirm", doc).textContent = Strings.CTX_CHANGE_YES;
    $("ctx-change-defer", doc).textContent = Strings.CTX_CHANGE_LATER;
    $("workspace-empty-note", doc).textContent = Strings.SECTION_EMPTY_PENDING;
    $("settings-kicker", doc).textContent = Strings.SETTINGS_KICKER;
    $("settings-title", doc).textContent = Strings.SETTINGS_TITLE;
    $("settings-subtitle", doc).textContent = Strings.SETTINGS_SUBTITLE;
    $("btn-back", doc).textContent = Strings.ACTION_BACK;
    $("settings-email-label", doc).textContent = Strings.SETTINGS_EMAIL_LABEL;
    $("settings-email", doc).placeholder = Strings.SETTINGS_EMAIL_PLACEHOLDER;
    $("settings-phone-cc-label", doc).textContent = Strings.SETTINGS_PHONE_CC_LABEL;
    $("settings-phone-cc", doc).placeholder = Strings.SETTINGS_PHONE_CC_PLACEHOLDER;
    $("settings-phone-label", doc).textContent = Strings.SETTINGS_PHONE_LABEL;
    $("settings-phone", doc).placeholder = Strings.SETTINGS_PHONE_PLACEHOLDER;
    $("btn-save-settings", doc).textContent = Strings.SETTINGS_SAVE;
    $("btn-reset-token", doc).textContent = Strings.SETTINGS_RESET;
  }

  function buildDisplayName(record) {
    const data = record.extraction_result?.data;
    if (data) {
      const nameParts = [];
      if (typeof data.GivenNamesEn === "string" && data.GivenNamesEn.trim()) {
        nameParts.push(data.GivenNamesEn.trim());
      } else if (Array.isArray(data.GivenNameTokensEn)) {
        nameParts.push(data.GivenNameTokensEn.filter(Boolean).join(" ").trim());
      }
      if (typeof data.SurnameEn === "string" && data.SurnameEn.trim()) {
        nameParts.push(data.SurnameEn.trim());
      }
      const name = nameParts.filter(Boolean).join(" ");
      if (name) {
        return name;
      }
    }
    return record.passport_number || Strings.RECORD_FALLBACK(record.upload_id);
  }

  function buildMeta(record) {
    const parts = [];
    const countryCode = record.extraction_result?.data?.CountryCode;
    if (countryCode) {
      parts.push(countryCode);
    }
    if (record.passport_number) {
      parts.push(`#${record.passport_number}`);
    }
    return parts.join(" · ");
  }

  function getClickUrl(record) {
    if (!record.masar_detail_id) {
      return null;
    }
    return `https://masar.nusuk.sa/umrah/mutamer/mutamer-details/${encodeURIComponent(record.masar_detail_id)}`;
  }

  function getStatusTone({ upload_status, masar_status, review_status, inProgress }) {
    if (upload_status === "failed" || masar_status === "failed") {
      return "red";
    }
    if (masar_status === "submitted" && review_status === "needs_review") {
      return "amber";
    }
    if (masar_status === "submitted") {
      return "green";
    }
    if (inProgress) {
      return "olive";
    }
    if (review_status === "needs_review") {
      return "amber";
    }
    return "green";
  }

  function getRecordVisualState(record) {
    if (record.upload_status === "failed" || record.masar_status === "failed") {
      return "failed";
    }
    if (record._inProgressState) {
      return "processing";
    }
    if (record.review_status === "needs_review") {
      return "review";
    }
    if (record.masar_status === "submitted" || record._section === "submitted") {
      return "success";
    }
    return "ready";
  }

  function getRecordNote(record) {
    if (record.review_status === "needs_review") {
      return Strings.REVIEW_SUMMARY;
    }
    if (record._section === "submitted") {
      return Strings.STATUS_SUBMITTED;
    }
    if (record._section === "failed") {
      return Strings.STATUS_FAILED;
    }
    if (record._inProgressState) {
      return Status.getStatusLabel({
        upload_status: record.upload_status,
        masar_status: record.masar_status,
        review_status: record.review_status,
        inProgress: record._inProgressState,
      });
    }
    return Strings.STATUS_READY;
  }

  function createStatusPill(doc, record, inProgressState) {
    const pill = doc.createElement("span");
    pill.className = `status-pill status-chip ${getStatusTone({
      upload_status: record.upload_status,
      masar_status: record.masar_status,
      review_status: record.review_status,
      inProgress: inProgressState,
    })}`;
    pill.textContent = Status.getStatusLabel({
      upload_status: record.upload_status,
      masar_status: record.masar_status,
      review_status: record.review_status,
      inProgress: inProgressState,
    });
    return pill;
  }

  function createPassportThumb(doc, record) {
    const thumb = doc.createElement("div");
    thumb.className = "passport-thumb";
    const top = doc.createElement("span");
    top.textContent = Strings.THUMBNAIL_LABEL;
    const bottom = doc.createElement("span");
    bottom.textContent = (record.passport_number || String(record.upload_id)).slice(-4);
    thumb.append(top, bottom);
    return thumb;
  }

  function renderHomeSummary(doc, { pendingCount, failedCount }) {
    const pending = $("pending-count", doc);
    const failed = $("failed-count", doc);
    pending.textContent = Strings.HOME_COUNT_VALUE(pendingCount);
    failed.textContent = Strings.HOME_COUNT_VALUE(failedCount);
    failed.dataset.tone = failedCount > 0 ? "danger" : "normal";
  }

  async function handleCardClick({ clickUrl }) {
    if (!clickUrl || typeof chrome === "undefined" || !chrome.tabs) {
      return false;
    }
    await chrome.tabs.create({ url: clickUrl });
    return true;
  }

  function createActionButton(doc, label, handler, options = {}) {
    const button = doc.createElement("button");
    button.type = "button";
    button.textContent = label;
    if (options.className) {
      button.className = options.className;
    }
    if (options.disabled) {
      button.disabled = true;
    }
    button.addEventListener("click", async () => {
      if (button.disabled) {
        return;
      }
      button.disabled = true;
      try {
        await handler();
      } catch {
        // Ignore to preserve previous popup behavior.
      }
    });
    return button;
  }

  function renderPendingCard(doc, record) {
    const article = doc.createElement("article");
    article.className = `record rich ${getRecordVisualState(record)}`;
    article.dataset.uploadId = String(record.upload_id);

    const body = doc.createElement("div");
    body.className = "record-body record-main";

    const header = doc.createElement("div");
    header.className = "record-header";
    const textWrap = doc.createElement("div");
    const name = doc.createElement("div");
    name.className = "record-name";
    name.textContent = buildDisplayName(record);
    const meta = doc.createElement("div");
    meta.className = "record-meta";
    meta.textContent = buildMeta(record);
    textWrap.append(name, meta);
    header.append(textWrap, createStatusPill(doc, record, record._inProgressState || false));

    const review = doc.createElement("div");
    review.className = "record-review";
    review.textContent = getRecordNote(record);

    const footer = doc.createElement("div");
    footer.className = "record-footer";
    const actions = doc.createElement("div");
    actions.className = "record-actions";

    if (record._section === "pending") {
      actions.append(
        createActionButton(doc, Strings.ACTION_SUBMIT, record._onSubmit, {
          disabled: Boolean(record._submitDisabled),
        }),
        createActionButton(doc, Strings.ACTION_SKIP, record._onSkip, { className: "ghost-btn" }),
      );
    } else if (record._section === "failed") {
      actions.append(
        createActionButton(doc, Strings.ACTION_RETRY, record._onRetry, {
          disabled: Boolean(record._submitDisabled),
        }),
      );
    } else if (record._section === "submitted") {
      const link = doc.createElement("a");
      link.className = `detail-link${record._clickUrl ? "" : " muted"}`;
      link.href = record._clickUrl || "#";
      link.textContent = record._clickUrl ? Strings.VIEW_DETAILS : Strings.DETAILS_UNAVAILABLE;
      link.addEventListener("click", (event) => {
        event.preventDefault();
        void handleCardClick({ clickUrl: record._clickUrl });
      });
      actions.append(link);
    }

    footer.append(actions);
    body.append(header, review, footer);
    article.append(createPassportThumb(doc, record), body);
    return article;
  }

  async function initContextChangeBanner(doc = document) {
    const banner = $("context-change-banner", doc);
    const reason = await ContextChange.getContextChangeReason();
    const pending = await ContextChange.hasContextChangePending();
    const text = $("context-change-text", doc);
    if (!pending || state.hiddenContextBanner) {
      banner.classList.add("hidden");
      return;
    }
    text.textContent =
      reason === "entity_changed" ? Strings.CTX_CHANGE_ENTITY : Strings.CTX_CHANGE_CONTRACT;
    banner.classList.remove("hidden");
  }

  function renderEmptyState(container, message) {
    container.innerHTML = "";
    const doc = container.ownerDocument;
    const empty = container.ownerDocument.createElement("div");
    empty.className = "empty-state";
    const mark = doc.createElement("div");
    mark.className = "empty-mark";
    mark.textContent = "—";
    const title = doc.createElement("div");
    title.className = "empty-title";
    title.textContent = message;
    empty.append(mark, title);
    container.appendChild(empty);
  }

  function setSectionVisibility(sectionName, doc = document) {
    const emptyHint = $("workspace-empty-note", doc);
    const title = $("pending-title", doc);
    const submitAll = $("submit-all-btn", doc);
    const titleMap = {
      pending: Strings.SECTION_PENDING,
      inProgress: Strings.SECTION_IN_PROGRESS,
      submitted: Strings.SECTION_SUBMITTED,
      failed: Strings.SECTION_FAILED,
    };
    if (title) {
      title.textContent = titleMap[sectionName] || Strings.SECTION_PENDING;
    }
    if (submitAll) {
      submitAll.classList.toggle("hidden", sectionName !== "pending");
    }
    if (!emptyHint) {
      return;
    }
    emptyHint.textContent =
      {
        pending: Strings.SECTION_EMPTY_PENDING,
        inProgress: Strings.SECTION_EMPTY_IN_PROGRESS,
        submitted: Strings.SECTION_EMPTY_SUBMITTED,
        failed: Strings.SECTION_EMPTY_FAILED,
      }[sectionName] || Strings.SECTION_EMPTY_PENDING;
  }

  function activateTab(tabName, doc = document) {
    state.activeTab = tabName;
    doc.querySelectorAll(".tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.tab === tabName);
    });
    const panels = {
      pending: "pending-section",
      inProgress: "in-progress-section",
      submitted: "submitted-section",
      failed: "failed-section",
    };
    Object.entries(panels).forEach(([name, id]) => {
      $(id, doc).classList.toggle("hidden", name !== tabName);
    });
    setSectionVisibility(tabName, doc);
  }

  function applySummaryContext(localData, doc = document) {
    $("ctx-entity", doc).textContent =
      localData.masar_user_name || localData.masar_entity_id || "—";
    $("ctx-contract", doc).textContent =
      localData.masar_contract_name_ar ||
      localData.masar_contract_name_en ||
      localData.masar_contract_id ||
      "—";
    $("ctx-group", doc).textContent = localData.masar_group_name || localData.masar_group_id || "—";
    const pill = $("contract-state-pill", doc);
    if (!localData.masar_contract_id && !localData.masar_contract_name_ar && !localData.masar_contract_name_en) {
      pill.classList.add("hidden");
      pill.textContent = "";
      pill.dataset.tone = "";
      return;
    }
    if (localData.masar_contract_state === "expired") {
      pill.textContent = Strings.CONTRACT_EXPIRED;
      pill.dataset.tone = "amber";
      pill.classList.remove("hidden");
    } else {
      pill.textContent = Strings.CONTRACT_ACTIVE;
      pill.dataset.tone = "green";
      pill.classList.remove("hidden");
    }
  }

  function populateTabCounts(sections, doc = document) {
    $("tab-count-pending", doc).textContent = String(sections.pending.length);
    $("tab-count-in-progress", doc).textContent = String(sections.inProgress.length);
    $("tab-count-submitted", doc).textContent = String(sections.submitted.length);
    $("tab-count-failed", doc).textContent = String(sections.failed.length);
  }

  async function populateContractDropdown(currentContractId, doc = document, { forceRefresh = false } = {}) {
    const container = $("contract-dropdown-container", doc);
    const select = $("contract-select", doc);
    select.innerHTML = "";
    select.append(new Option(Strings.CONTRACT_SELECT_PLACEHOLDER, ""));
    try {
      const now = Date.now();
      const shouldUseCache =
        !forceRefresh
        && Array.isArray(state.contractsCache)
        && (now - state.contractsCacheAt) < CONTRACT_CACHE_TTL_MS;
      const contracts = shouldUseCache ? state.contractsCache : await ContractSelect.fetchContracts();
      if (!shouldUseCache) {
        state.contractsCache = contracts;
        state.contractsCacheAt = now;
      }
      const resolution = ContractSelect.resolveContractSelection(contracts, currentContractId);
      const activeContracts = contracts.filter((contract) => contract?.contractStatus?.id === 0);
      if (activeContracts.length === 0) {
        container.classList.remove("hidden");
        select.append(new Option(Strings.CONTRACT_NONE_AVAILABLE, ""));
        select.disabled = true;
        return;
      }
      activeContracts.forEach((contract) => {
        const option = new Option(
          contract.companyNameAr || contract.companyNameEn || String(contract.contractId),
          String(contract.contractId),
        );
        select.append(option);
      });
      select.disabled = false;
      container.classList.toggle("hidden", !resolution.showDropdown);
      if (resolution.selectedContract) {
        select.value = String(resolution.selectedContract.contractId);
      } else if (currentContractId) {
        select.value = String(currentContractId);
      }
    } catch {
      container.classList.add("hidden");
    }
  }

  function renderSection(containerId, records, sectionName, emptyText, doc = document) {
    const container = $(containerId, doc);
    container.innerHTML = "";
    if (records.length === 0) {
      renderEmptyState(container, emptyText);
      return;
    }
    for (const record of records) {
      const sectionRecord = { ...record, _section: sectionName };
      container.appendChild(renderPendingCard(doc, sectionRecord));
    }
  }

  function applyLastSubmitResult(records, result) {
    if (!result || typeof result !== "object" || !result.upload_id) {
      return records;
    }
    return (Array.isArray(records) ? records : []).map((record) => {
      if (record.upload_id !== result.upload_id) {
        return record;
      }
      if (result.status === "submitted") {
        return {
          ...record,
          masar_status: "submitted",
          masar_detail_id: result.masar_detail_id || record.masar_detail_id || null,
        };
      }
      if (result.status === "failed") {
        return {
          ...record,
          masar_status: "failed",
        };
      }
      return record;
    });
  }

  async function submitSingle(record) {
    const response = await sendMsg({ type: "SUBMIT_RECORD", record }, { timeoutMs: 60000 });
    await handleSubmitResponse({
      response,
      classifyFailure: Failure.classifyFailure,
      onRelinkRequired: showRelinkRequired,
      onMasarLoginRequired: async () => {
        showMasarLoginRequired();
        return "login";
      },
      onReload: async () => {
        await loadMainWorkspace({ showLoading: false, fetchRecords: true });
        return "reload";
      },
    });
  }

  async function submitBatch(uploadIds) {
    if (!uploadIds.length) {
      return;
    }
    const confirmed = window.confirm(Strings.SUBMIT_ALL_CONFIRM(uploadIds.length));
    if (!confirmed) {
      return;
    }
    const response = await sendMsg({ type: "SUBMIT_BATCH", uploadIds }, { timeoutMs: 30000 });
    await handleSubmitResponse({
      response,
      classifyFailure: Failure.classifyFailure,
      onRelinkRequired: showRelinkRequired,
      onMasarLoginRequired: async () => {
        showMasarLoginRequired();
        return "login";
      },
      onReload: async () => {
        await loadMainWorkspace({ showLoading: false, fetchRecords: true });
        return "reload";
      },
    });
  }

  async function loadMainWorkspace({ showLoading = true, fetchRecords = true, refreshContracts = false } = {}) {
    if (state.isWorkspaceLoading) {
      state.hasQueuedWorkspaceReload = true;
      return;
    }
    state.isWorkspaceLoading = true;
    if (showLoading) {
      showScreen("loading");
    }
    try {
      const [localData, sessionData, recordsResponse] = await Promise.all([
        localGet([
          "masar_entity_id",
          "masar_user_name",
          "masar_contract_id",
          "submit_auth_required",
          "masar_contract_name_ar",
          "masar_contract_name_en",
          "masar_contract_state",
          "masar_group_id",
          "masar_group_name",
        ]),
        sessionGet(["submission_batch", "active_submit_id", "last_submit_result"]),
        fetchRecords
          ? sendMsg({ type: "FETCH_ALL_RECORDS" }, { timeoutMs: 30000 })
          : Promise.resolve({ ok: true, data: state.lastFetchedRecords }),
      ]);

      if (!recordsResponse?.ok) {
        const failure = Failure.classifyFailure(recordsResponse);
        if (failure.type === "relink") {
          await showRelinkRequired();
          return;
        }
        showError(recordsResponse?.error || Strings.ERR_UNEXPECTED);
        return;
      }

      if (localData.submit_auth_required === "masar-auth") {
        showMasarLoginRequired();
        return;
      }
      if (localData.submit_auth_required === "backend-auth") {
        await showRelinkRequired();
        return;
      }

      const recordsData = Array.isArray(recordsResponse.data) ? recordsResponse.data : [];
      state.lastFetchedRecords = fetchRecords
        ? recordsData
        : applyLastSubmitResult(recordsData, sessionData.last_submit_result);
      const inProgressIds = new Set(sessionData.submission_batch || []);
      const activeSubmitId = sessionData.active_submit_id || null;
      const sections = QueueFilter.filterQueueSections(state.lastFetchedRecords, inProgressIds);
      const pendingVisible = sections.pending.filter((record) => !state.skippedIds.has(record.upload_id));
      const contractExpired = localData.masar_contract_state === "expired";
      const canSubmit = Boolean(localData.masar_contract_id) && !contractExpired;

      state.sectionData = sections;
      applySummaryContext(localData);
      renderHomeSummary(document, {
        pendingCount: pendingVisible.length,
        failedCount: sections.failed.length,
      });
      populateTabCounts({
        pending: pendingVisible,
        inProgress: sections.inProgress,
        submitted: sections.submitted,
        failed: sections.failed,
      });

      const pendingRecords = pendingVisible.map((record) => ({
        ...record,
        _submitDisabled: !canSubmit,
        _onSubmit: () => submitSingle(record),
        _onSkip: () => {
          state.skippedIds.add(record.upload_id);
          return loadMainWorkspace({ showLoading: false, fetchRecords: false });
        },
      }));
      const inProgressRecords = sections.inProgress.map((record) => ({
        ...record,
        _inProgressState: record.upload_id === activeSubmitId ? "active" : "queued",
      }));
      const submittedRecords = sections.submitted.map((record) => ({
        ...record,
        _clickUrl: getClickUrl(record),
      }));
      const failedRecords = sections.failed.map((record) => ({
        ...record,
        _submitDisabled: !canSubmit,
        _onRetry: () => submitSingle(record),
      }));

      renderSection("pending-list", pendingRecords, "pending", Strings.SECTION_EMPTY_PENDING);
      renderSection(
        "in-progress-list",
        inProgressRecords,
        "inProgress",
        Strings.SECTION_EMPTY_IN_PROGRESS,
      );
      renderSection(
        "submitted-list",
        submittedRecords,
        "submitted",
        Strings.SECTION_EMPTY_SUBMITTED,
      );
      renderSection("failed-list", failedRecords, "failed", Strings.SECTION_EMPTY_FAILED);
      $("submit-all-btn").disabled = !canSubmit || pendingRecords.length === 0;
      $("submit-all-btn").onclick = () => void submitBatch(pendingRecords.map((record) => record.upload_id));
      await populateContractDropdown(localData.masar_contract_id, document, { forceRefresh: refreshContracts });
      await initContextChangeBanner();
      showScreen("main");
      activateTab(state.activeTab);
    } finally {
      state.isWorkspaceLoading = false;
      if (state.hasQueuedWorkspaceReload) {
        state.hasQueuedWorkspaceReload = false;
        void loadMainWorkspace({ showLoading: false, fetchRecords: true, refreshContracts: false });
      }
    }
  }

  async function loadGroupPicker() {
    showScreen("group-select");
    const response = await sendMsg({ type: "FETCH_GROUPS" });
    const select = $("group-select");
    select.innerHTML = "";
    if (!response?.ok) {
      $("group-select-hint").classList.remove("hidden");
      select.append(new Option(Strings.GROUP_LOAD_FAILED, ""));
      return;
    }
    $("group-select-hint").classList.add("hidden");
    const groups = response.data?.response?.data?.content || [];
    if (!groups.length) {
      $("group-select-hint").classList.remove("hidden");
      select.append(new Option(Strings.GROUP_NONE_FOUND, ""));
      return;
    }
    for (const group of groups) {
      const option = new Option(group.groupName || group.groupNumber || String(group.id), String(group.id));
      option.dataset.groupName = group.groupName || "";
      option.dataset.groupNumber = group.groupNumber || "";
      select.append(option);
    }
  }

  function populateSettings(values) {
    $("settings-email").value = values.agency_email || "";
    $("settings-phone-cc").value = values.agency_phone_country_code || "966";
    $("settings-phone").value = values.agency_phone || "";
  }

  function showError(message) {
    $("error-detail").textContent = message;
    showScreen("error");
  }

  function showSetupError(message) {
    const banner = $("setup-error");
    banner.textContent = message || "";
    banner.classList.toggle("hidden", !message);
  }

  function showMasarLoginRequired() {
    $("session-expired-text").textContent = Strings.MASAR_LOGIN_REQUIRED;
    showScreen("session-expired");
  }

  async function showRelinkRequired() {
    await localRemove(["api_token", "submit_auth_required"]);
    showSetupError(Strings.SETUP_RELINK_REQUIRED);
    showScreen("setup");
  }

  async function init() {
    showScreen("loading");
    const stored = await localGet([
      "api_token",
      "masar_entity_id",
      "masar_group_id",
      "agency_email",
      "agency_phone",
      "agency_phone_country_code",
    ]);
    if (!stored.api_token) {
      showSetupError("");
      showScreen("setup");
      return;
    }
    if (!stored.masar_entity_id) {
      showScreen("activate");
      return;
    }

    await sendMsg({ type: "SYNC_SESSION" });
    const refreshed = await localGet(["masar_group_id"]);
    if (!refreshed.masar_group_id) {
      await loadGroupPicker();
      return;
    }
    await loadMainWorkspace({ showLoading: true, fetchRecords: true });
  }

  async function bootstrap() {
    setStaticCopy();
    bindEvents();
    await init();
  }

  async function handleSubmitResponse({
    response,
    classifyFailure,
    onRelinkRequired,
    onMasarLoginRequired,
    onReload,
  }) {
    if (response?.ok) {
      return onReload();
    }
    const failure = classifyFailure(response);
    if (failure.type === "relink") {
      return onRelinkRequired();
    }
    if (failure.type === "masar-login") {
      return onMasarLoginRequired();
    }
    return onReload();
  }

  async function handleContractSelectionChange({ value, writeSelection, reloadWorkspace }) {
    await writeSelection({
      masar_contract_id: value,
      masar_contract_manual_override: true,
    });
    await reloadWorkspace();
  }

  function scheduleWorkspaceReload({ fetchRecords = true, refreshContracts = false } = {}) {
    state.pendingReloadFetchRecords = state.pendingReloadFetchRecords || fetchRecords;
    state.pendingReloadRefreshContracts =
      state.pendingReloadRefreshContracts || refreshContracts;
    if (state.pendingReloadTimer) {
      clearTimeout(state.pendingReloadTimer);
    }
    state.pendingReloadTimer = setTimeout(() => {
      const shouldFetchRecords = state.pendingReloadFetchRecords;
      const shouldRefreshContracts = state.pendingReloadRefreshContracts;
      state.pendingReloadFetchRecords = false;
      state.pendingReloadRefreshContracts = false;
      state.pendingReloadTimer = null;
      void loadMainWorkspace({
        showLoading: false,
        fetchRecords: shouldFetchRecords,
        refreshContracts: shouldRefreshContracts,
      });
    }, 200);
  }

  function bindEvents() {
    $("btn-save-token").addEventListener("click", async () => {
      const button = $("btn-save-token");
      button.disabled = true;
      showSetupError("");
      try {
        const issued = await Auth.exchangeTempToken({
          apiBaseUrl,
          tempToken: $("api-token-input").value.trim(),
          fetchImpl: fetch,
        });
        await localSet({ api_token: issued.sessionToken });
        $("api-token-input").value = "";
        await init();
      } catch (error) {
        showSetupError(Strings.SETUP_LOGIN_FAILED(error?.message || ""));
      } finally {
        button.disabled = false;
      }
    });

    $("btn-open-masar-activate").addEventListener("click", () => {
      void sendMsg({ type: "OPEN_MASAR" });
    });
    $("btn-open-masar-expired").addEventListener("click", () => {
      void sendMsg({ type: "OPEN_MASAR" });
    });
    $("btn-confirm-group").addEventListener("click", async () => {
      const select = $("group-select");
      if (!select.value) {
        return;
      }
      const button = $("btn-confirm-group");
      button.disabled = true;
      const option = select.options[select.selectedIndex];
      try {
        await localSet({
          masar_group_id: select.value,
          masar_group_name: option?.dataset.groupName || "",
          masar_group_number: option?.dataset.groupNumber || "",
        });
        await loadMainWorkspace({ showLoading: true, fetchRecords: true });
      } finally {
        button.disabled = false;
      }
    });
    $("btn-settings").addEventListener("click", async () => {
      populateSettings(
        await localGet(["agency_email", "agency_phone", "agency_phone_country_code"]),
      );
      showScreen("settings");
    });
    $("btn-back").addEventListener("click", () => {
      void init();
    });
    $("btn-save-settings").addEventListener("click", async () => {
      await localSet({
        agency_email: $("settings-email").value.trim(),
        agency_phone_country_code: $("settings-phone-cc").value.trim(),
        agency_phone: $("settings-phone").value.trim(),
      });
      await init();
    });
    $("btn-reset-token").addEventListener("click", async () => {
      await localRemove(["api_token", "masar_group_id"]);
      showScreen("setup");
    });
    $("btn-change-group").addEventListener("click", async () => {
      await localRemove(["masar_group_id", "masar_group_name", "masar_group_number"]);
      await loadGroupPicker();
    });
    $("btn-refresh-context").addEventListener("click", async () => {
      await sendMsg({ type: "SYNC_SESSION" });
      await init();
    });
    $("ctx-change-confirm").addEventListener("click", async () => {
      state.hiddenContextBanner = false;
      await sendMsg({ type: "APPLY_CONTEXT_CHANGE" });
      await init();
    });
    $("ctx-change-defer").addEventListener("click", async () => {
      state.hiddenContextBanner = true;
      await initContextChangeBanner();
    });
    $("contract-select").addEventListener("change", async (event) => {
      if (!event.target.value) {
        return;
      }
      await handleContractSelectionChange({
        value: event.target.value,
        writeSelection: localSet,
        reloadWorkspace: () => loadMainWorkspace({ showLoading: false, fetchRecords: true }),
      });
    });
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => activateTab(tab.dataset.tab));
    });
    chrome.storage.onChanged.addListener((changes, areaName) => {
      const isMainScreenVisible = !$("screen-main").classList.contains("hidden");
      if (shouldRefreshWorkspaceForStorageChange({ areaName, changes, isMainScreenVisible })) {
        const fetchRecords = false;
        const refreshContracts =
          areaName === "local"
          && (
            Object.prototype.hasOwnProperty.call(changes, "masar_contract_id")
            || Object.prototype.hasOwnProperty.call(changes, "masar_contract_state")
          );
        scheduleWorkspaceReload({ fetchRecords, refreshContracts });
      }
    });
  }

  return {
    bootstrap,
    getScreenTheme,
    handleCardClick,
    handleContractSelectionChange,
    handleSubmitResponse,
    initContextChangeBanner,
    renderHomeSummary,
    renderPendingCard,
    shouldRefreshWorkspaceForStorageChange,
  };
});
