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
  };

  function $(id, doc = document) {
    return doc.getElementById(id);
  }

  function showScreen(name, doc = document) {
    doc.querySelectorAll(".screen").forEach((element) => element.classList.add("hidden"));
    const screen = $(`screen-${name}`, doc);
    if (screen) {
      screen.classList.remove("hidden");
    }
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

  function sendMsg(message) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => resolve({ ok: false, error: Strings.ERR_TIMEOUT }), 15000);
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
    $("help-support-link", doc).textContent = Strings.HELP_LINK_LABEL;
    $("help-support-link", doc).href = apiBaseUrl || "#";
    $("btn-settings", doc).textContent = Strings.ACTION_SETTINGS;
    $("loading-text", doc).textContent = Strings.LOADING;
    $("error-title", doc).textContent = Strings.ERROR_TITLE;
    $("setup-title", doc).textContent = Strings.SETUP_TITLE;
    $("setup-token-label", doc).textContent = Strings.SETUP_TOKEN_LABEL;
    $("api-token-input", doc).placeholder = Strings.SETUP_TOKEN_PLACEHOLDER;
    $("btn-save-token", doc).textContent = Strings.SETUP_SAVE;
    $("activate-message", doc).textContent = Strings.ACTIVATE_MESSAGE;
    $("btn-open-masar-activate", doc).textContent = Strings.OPEN_LOGIN;
    $("btn-open-masar-expired", doc).textContent = Strings.OPEN_LOGIN;
    $("group-title", doc).textContent = Strings.GROUP_TITLE;
    $("group-select-hint", doc).textContent = Strings.GROUP_HINT;
    $("btn-confirm-group", doc).textContent = Strings.GROUP_CONFIRM;
    $("home-office-label", doc).textContent = Strings.HOME_OFFICE_LABEL;
    $("home-contract-label", doc).textContent = Strings.HOME_CONTRACT_LABEL;
    $("home-pending-label", doc).textContent = Strings.HOME_PENDING_LABEL;
    $("home-failed-label", doc).textContent = Strings.HOME_FAILED_LABEL;
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
    $("settings-title", doc).textContent = Strings.SETTINGS_TITLE;
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

  function createStatusPill(doc, record, inProgressState) {
    const pill = doc.createElement("span");
    pill.className = "status-pill";
    pill.textContent = Status.getStatusLabel({
      upload_status: record.upload_status,
      masar_status: record.masar_status,
      review_status: record.review_status,
      inProgress: inProgressState,
    });
    pill.style.background = Status.getStatusColor({
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
    button.addEventListener("click", handler);
    return button;
  }

  function renderPendingCard(doc, record) {
    const article = doc.createElement("article");
    article.className = "record rich";
    article.dataset.uploadId = String(record.upload_id);

    const body = doc.createElement("div");
    body.className = "record-body";

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
    review.textContent =
      record.review_status === "needs_review" ? Strings.REVIEW_SUMMARY : Strings.STATUS_READY;

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
    const empty = container.ownerDocument.createElement("div");
    empty.className = "empty-state";
    empty.textContent = message;
    container.appendChild(empty);
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
    if (localData.masar_contract_state === "expired") {
      pill.textContent = Strings.CONTRACT_EXPIRED;
      pill.classList.remove("hidden");
    } else {
      pill.classList.add("hidden");
      pill.textContent = "";
    }
  }

  function populateTabCounts(sections, doc = document) {
    $("tab-count-pending", doc).textContent = String(sections.pending.length);
    $("tab-count-in-progress", doc).textContent = String(sections.inProgress.length);
    $("tab-count-submitted", doc).textContent = String(sections.submitted.length);
    $("tab-count-failed", doc).textContent = String(sections.failed.length);
  }

  async function populateContractDropdown(currentContractId, doc = document) {
    const container = $("contract-dropdown-container", doc);
    const select = $("contract-select", doc);
    select.innerHTML = "";
    select.append(new Option(Strings.CONTRACT_SELECT_PLACEHOLDER, ""));
    try {
      const contracts = await ContractSelect.fetchContracts();
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
        if (!currentContractId) {
          void localSet({ masar_contract_id: String(resolution.selectedContract.contractId) });
        }
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

  async function submitSingle(record) {
    const response = await sendMsg({ type: "SUBMIT_RECORD", record });
    await handleSubmitResponse({
      response,
      classifyFailure: Failure.classifyFailure,
      onRelinkRequired: showRelinkRequired,
      onMasarLoginRequired: async () => {
        showMasarLoginRequired();
        return "login";
      },
      onReload: async () => {
        await loadMainWorkspace();
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
    const response = await sendMsg({ type: "SUBMIT_BATCH", uploadIds });
    await handleSubmitResponse({
      response,
      classifyFailure: Failure.classifyFailure,
      onRelinkRequired: showRelinkRequired,
      onMasarLoginRequired: async () => {
        showMasarLoginRequired();
        return "login";
      },
      onReload: async () => {
        await loadMainWorkspace();
        return "reload";
      },
    });
  }

  async function loadMainWorkspace() {
    showScreen("loading");
    const [localData, sessionData, recordsResponse] = await Promise.all([
      localGet([
        "masar_entity_id",
        "masar_user_name",
        "masar_contract_id",
        "masar_contract_name_ar",
        "masar_contract_name_en",
        "masar_contract_state",
        "masar_group_id",
        "masar_group_name",
      ]),
      sessionGet(["submission_batch", "active_submit_id"]),
      sendMsg({ type: "FETCH_ALL_RECORDS" }),
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

    const inProgressIds = new Set(sessionData.submission_batch || []);
    const activeSubmitId = sessionData.active_submit_id || null;
    const sections = QueueFilter.filterQueueSections(recordsResponse.data || [], inProgressIds);
    const pendingVisible = sections.pending.filter((record) => !state.skippedIds.has(record.upload_id));
    const contractExpired = localData.masar_contract_state === "expired";

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
      _submitDisabled: contractExpired,
      _onSubmit: () => void submitSingle(record),
      _onSkip: () => {
        state.skippedIds.add(record.upload_id);
        void loadMainWorkspace();
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
      _submitDisabled: contractExpired,
      _onRetry: () => void submitSingle(record),
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
    $("submit-all-btn").disabled = contractExpired || pendingRecords.length === 0;
    $("submit-all-btn").onclick = () => void submitBatch(pendingRecords.map((record) => record.upload_id));
    await populateContractDropdown(localData.masar_contract_id);
    await initContextChangeBanner();
    showScreen("main");
    activateTab(state.activeTab);
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
    await localRemove(["api_token"]);
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
    await loadMainWorkspace();
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
      const option = select.options[select.selectedIndex];
      await localSet({
        masar_group_id: select.value,
        masar_group_name: option?.dataset.groupName || "",
        masar_group_number: option?.dataset.groupNumber || "",
      });
      await loadMainWorkspace();
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
      await handleContractSelectionChange({
        value: event.target.value,
        writeSelection: localSet,
        reloadWorkspace: loadMainWorkspace,
      });
    });
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => activateTab(tab.dataset.tab));
    });
    chrome.storage.onChanged.addListener((_changes, areaName) => {
      if (areaName === "local" || areaName === "session") {
        void loadMainWorkspace();
      }
    });
  }

  return {
    bootstrap,
    handleCardClick,
    handleContractSelectionChange,
    handleSubmitResponse,
    initContextChangeBanner,
    renderHomeSummary,
    renderPendingCard,
  };
});
