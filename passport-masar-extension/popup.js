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
  function createTabCacheState(loaded = false) {
    return {
      items: [],
      total: 0,
      offset: 0,
      hasMore: false,
      loaded,
      loading: false,
      error: null,
      lastLoadedAt: 0,
    };
  }

  const state = {
    activeTab: "pending",
    hiddenContextBanner: false,
    pendingRecords: [],
    skippedIds: new Set(),
    sectionData: null,
    tabCache: {
      pending: createTabCacheState(),
      inProgress: createTabCacheState(true),
      submitted: createTabCacheState(),
      failed: createTabCacheState(),
    },
    countsState: {
      server: null,
      stale: false,
      loading: false,
    },
    lastLocalData: null,
    lastSessionData: null,
    isWorkspaceLoading: false,
    hasQueuedWorkspaceReload: false,
    contractsCache: null,
    contractsCacheAt: 0,
    toastTimer: null,
  };
  const CONTRACT_CACHE_TTL_MS = 30000;

  function $(id, doc = document) {
    return doc.getElementById(id);
  }

  function getScreenTheme(name) {
    switch (name) {
      case "setup":
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
    const setText = (id, value) => {
      const element = $(id, doc);
      if (element) {
        element.textContent = value;
      }
    };
    const setPlaceholder = (id, value) => {
      const element = $(id, doc);
      if (element) {
        element.placeholder = value;
      }
    };
    doc.title = Strings.TOPBAR_TITLE;
    setText("topbar-title", Strings.TOPBAR_TITLE);
    setText("topbar-kicker", Strings.TOPBAR_KICKER);
    if ($("help-support-link", doc)) {
      $("help-support-link", doc).textContent = "؟";
      $("help-support-link", doc).title = Strings.HELP_LINK_LABEL;
      $("help-support-link", doc).ariaLabel = Strings.HELP_LINK_LABEL;
      $("help-support-link", doc).href = apiBaseUrl || "#";
    }
    if ($("btn-settings", doc)) {
      $("btn-settings", doc).textContent = "⚙";
      $("btn-settings", doc).title = Strings.ACTION_SETTINGS;
      $("btn-settings", doc).ariaLabel = Strings.ACTION_SETTINGS;
    }
    setText("loading-kicker", Strings.LOADING_KICKER);
    setText("loading-title", Strings.LOADING);
    setText("loading-subtitle", Strings.LOADING_SUBTITLE);
    setText("loading-text", Strings.LOADING_HINT);
    setText("error-kicker", Strings.ERROR_KICKER);
    setText("error-title", Strings.ERROR_TITLE);
    setText("error-subtitle", Strings.ERROR_SUBTITLE);
    setText("setup-kicker", Strings.SETUP_KICKER);
    setText("setup-title", Strings.SETUP_TITLE);
    setText("setup-subtitle", Strings.SETUP_SUBTITLE);
    setText("setup-token-label", Strings.SETUP_TOKEN_LABEL);
    setPlaceholder("api-token-input", Strings.SETUP_TOKEN_PLACEHOLDER);
    setText("btn-save-token", Strings.SETUP_SAVE);
    setText("setup-helper", Strings.SETUP_HELP);
    setText("activate-kicker", Strings.ACTIVATE_KICKER);
    setText("activate-title", Strings.ACTIVATE_TITLE);
    setText("activate-subtitle", Strings.ACTIVATE_SUBTITLE);
    setText("activate-message", Strings.ACTIVATE_MESSAGE);
    setText("btn-open-masar-activate", Strings.OPEN_LOGIN);
    setText("session-kicker", Strings.SESSION_KICKER);
    setText("session-title", Strings.SESSION_EXPIRED);
    setText("session-subtitle", Strings.SESSION_SUBTITLE);
    setText("btn-open-masar-expired", Strings.OPEN_LOGIN);
    setText("main-kicker", Strings.MAIN_KICKER);
    setText("main-title", Strings.MAIN_TITLE);
    setText("main-subtitle", Strings.MAIN_SUBTITLE);
    setText("workspace-summary-title", Strings.MAIN_SUMMARY_TITLE);
    setText("workspace-summary-subtitle", Strings.MAIN_SUMMARY_SUBTITLE);
    setText("home-office-label", Strings.HOME_OFFICE_LABEL);
    setText("home-contract-label", Strings.HOME_CONTRACT_LABEL);
    setText("home-group-label", Strings.HOME_GROUP_LABEL);
    setText("home-pending-label", Strings.HOME_PENDING_LABEL);
    setText("home-failed-label", Strings.HOME_FAILED_LABEL);
    setText("contract-select-label", Strings.CONTRACT_SELECT_LABEL);
    setText("btn-refresh-context", Strings.ACTION_REFRESH);
    setText("tab-label-pending", Strings.SECTION_PENDING);
    setText("tab-label-in-progress", Strings.SECTION_IN_PROGRESS);
    setText("tab-label-submitted", Strings.SECTION_SUBMITTED);
    setText("tab-label-failed", Strings.SECTION_FAILED);
    setText("pending-title", Strings.SECTION_PENDING);
    setText("in-progress-title", Strings.SECTION_IN_PROGRESS);
    setText("submitted-title", Strings.SECTION_SUBMITTED);
    setText("failed-title", Strings.SECTION_FAILED);
    setText("submit-all-btn", Strings.ACTION_SUBMIT_ALL);
    setText("submission-progress-title", Strings.PROGRESS_BANNER_TITLE);
    setText("submission-refresh-btn", Strings.ACTION_REFRESH);
    setText("submission-resume-btn", Strings.ACTION_RESUME);
    setText("pending-load-more", Strings.ACTION_LOAD_MORE);
    setText("submitted-load-more", Strings.ACTION_LOAD_MORE);
    setText("failed-load-more", Strings.ACTION_LOAD_MORE);
    setText("ctx-change-confirm", Strings.CTX_CHANGE_YES);
    setText("ctx-change-defer", Strings.CTX_CHANGE_LATER);
    setText("workspace-empty-note", Strings.SECTION_EMPTY_PENDING);
    setText("settings-kicker", Strings.SETTINGS_KICKER);
    setText("settings-title", Strings.SETTINGS_TITLE);
    setText("settings-subtitle", Strings.SETTINGS_SUBTITLE);
    setText("btn-back", Strings.ACTION_BACK);
    setText("settings-email-label", Strings.SETTINGS_EMAIL_LABEL);
    setPlaceholder("settings-email", Strings.SETTINGS_EMAIL_PLACEHOLDER);
    setText("settings-phone-cc-label", Strings.SETTINGS_PHONE_CC_LABEL);
    setPlaceholder("settings-phone-cc", Strings.SETTINGS_PHONE_CC_PLACEHOLDER);
    setText("settings-phone-label", Strings.SETTINGS_PHONE_LABEL);
    setPlaceholder("settings-phone", Strings.SETTINGS_PHONE_PLACEHOLDER);
    setText("btn-save-settings", Strings.SETTINGS_SAVE);
    setText("btn-reset-token", Strings.SETTINGS_RESET);
  }

  function buildDisplayName(record) {
    if (typeof record.full_name_ar === "string" && record.full_name_ar.trim()) {
      return record.full_name_ar.trim();
    }
    if (typeof record.full_name_en === "string" && record.full_name_en.trim()) {
      return record.full_name_en.trim();
    }
    const data = record.extraction_result?.data;
    if (data) {
      const nameParts = [];
      if (typeof data.GivenNamesAr === "string" && data.GivenNamesAr.trim()) {
        nameParts.push(data.GivenNamesAr.trim());
      } else if (Array.isArray(data.GivenNameTokensAr)) {
        nameParts.push(data.GivenNameTokensAr.filter(Boolean).join(" ").trim());
      } else if (typeof data.GivenNamesEn === "string" && data.GivenNamesEn.trim()) {
        nameParts.push(data.GivenNamesEn.trim());
      } else if (Array.isArray(data.GivenNameTokensEn)) {
        nameParts.push(data.GivenNameTokensEn.filter(Boolean).join(" ").trim());
      }
      if (typeof data.SurnameAr === "string" && data.SurnameAr.trim()) {
        nameParts.push(data.SurnameAr.trim());
      } else if (typeof data.SurnameEn === "string" && data.SurnameEn.trim()) {
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
    const countryCode = record.country_code || record.extraction_result?.data?.CountryCode;
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

  function getSubmissionContextMismatch(record, localData = {}) {
    if (!record || record.masar_status !== "submitted") {
      return null;
    }
    const currentEntityId = localData.masar_entity_id || null;
    const currentContractId = localData.masar_contract_id || null;
    if (record.submission_entity_id && currentEntityId && record.submission_entity_id !== currentEntityId) {
      return "entity";
    }
    if (record.submission_contract_id && currentContractId && record.submission_contract_id !== currentContractId) {
      return "contract";
    }
    return null;
  }

  function getSubmissionContextMismatchToast(mismatch) {
    if (mismatch === "entity") {
      return Strings.DETAILS_OPEN_FROM_OTHER_ENTITY;
    }
    if (mismatch === "contract") {
      return Strings.DETAILS_OPEN_FROM_OTHER_CONTRACT;
    }
    return Strings.DETAILS_INACCESSIBLE;
  }

  function ensureActionContextState({
    activeUiContext,
    selectedContractId,
  }) {
    const context = ContextChange.normalizeActiveUiContext(activeUiContext);
    const contractId = selectedContractId || context.contract_id || null;
    if (context.requires_contract_confirmation || !contractId) {
      return { ok: false, reason: "contract" };
    }
    if (context.contract_state === "expired" || context.contract_state === "inactive") {
      return { ok: false, reason: "contract-inactive" };
    }
    return { ok: true, reason: null };
  }

  function getStatusTone({ upload_status, masar_status, review_status, inProgress, contextMismatch }) {
    if (upload_status === "failed" || masar_status === "failed") {
      return "red";
    }
    if (contextMismatch) {
      return "amber";
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
    if (record.masar_status === "missing") {
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
    if (record.failure_reason_code === "scan-image-unclear") {
      return Strings.FAILURE_REASON_SCAN_IMAGE_UNCLEAR;
    }
    if (record.failure_reason_code === "contract-missing") {
      return Strings.FAILURE_REASON_CONTRACT_MISSING;
    }
    if (record.failure_reason_code === "contract-inactive") {
      return Strings.FAILURE_REASON_CONTRACT_INACTIVE;
    }
    if (typeof record.failure_reason_text === "string" && record.failure_reason_text.trim()) {
      const normalized = record.failure_reason_text.trim().toLowerCase();
      if (normalized.includes("passport image is not clear")) {
        return Strings.FAILURE_REASON_SCAN_IMAGE_UNCLEAR;
      }
      if (normalized.includes("no active contract")) {
        return Strings.FAILURE_REASON_CONTRACT_INACTIVE;
      }
      if (normalized.includes("no contract sent in request")) {
        return Strings.FAILURE_REASON_CONTRACT_MISSING;
      }
    }
    if (record.masar_status === "missing") {
      return Strings.DETAILS_RECORD_MISSING;
    }
    if (record._contextMismatch === "entity") {
      return Strings.DETAILS_OTHER_ENTITY;
    }
    if (record._contextMismatch === "contract") {
      return Strings.DETAILS_OTHER_CONTRACT;
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
      contextMismatch: record._contextMismatch,
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

  function showToast(message, { tone = "neutral", durationMs = 2200 } = {}) {
    if (typeof document === "undefined") {
      return;
    }
    const toast = $("app-toast");
    if (!toast) {
      return;
    }
    if (state.toastTimer) {
      clearTimeout(state.toastTimer);
      state.toastTimer = null;
    }
    toast.textContent = message || "";
    toast.dataset.tone = tone;
    toast.classList.toggle("hidden", !message);
    if (!message || durationMs <= 0) {
      return;
    }
    state.toastTimer = setTimeout(() => {
      toast.classList.add("hidden");
      toast.textContent = "";
      toast.dataset.tone = "";
      state.toastTimer = null;
    }, durationMs);
  }

  async function handleCardClick({
    clickUrl,
    uploadId = null,
    detailsContext = null,
    onMissingRecord = null,
    onInaccessible = null,
    onOpenStart = null,
    onOpenFailed = null,
  }) {
    if (!clickUrl || typeof chrome === "undefined" || !chrome.runtime?.sendMessage) {
      return false;
    }
    if (typeof onOpenStart === "function") {
      onOpenStart(Strings.DETAILS_OPENING);
    }
    const response = await sendMsg(
      { type: "OPEN_MUTAMER_DETAILS_EXPERIMENT", clickUrl, uploadId, detailsContext },
      { timeoutMs: 60000 },
    );
    if (response?.errorCode === "mutamer-missing" && typeof onMissingRecord === "function") {
      await onMissingRecord(Strings.DETAILS_RECORD_MISSING);
      return false;
    }
    if (response?.errorCode === "mutamer-inaccessible" && typeof onInaccessible === "function") {
      await onInaccessible(Strings.DETAILS_INACCESSIBLE);
      return false;
    }
    if (!response?.ok && typeof onOpenFailed === "function") {
      await onOpenFailed(Strings.DETAILS_OPEN_FAILED);
    }
    return Boolean(response?.ok);
  }

  function setDetailLinkLoadingState(link, isLoading, originalLabel) {
    if (!link) {
      return;
    }
    if (isLoading) {
      if (!link.dataset.originalLabel) {
        link.dataset.originalLabel = originalLabel || link.textContent || "";
      }
      link.textContent = Strings.DETAILS_OPENING;
      link.classList.add("muted");
      link.setAttribute("aria-disabled", "true");
      link.dataset.loading = "true";
      return;
    }
    const restoredLabel = link.dataset.originalLabel || originalLabel || link.textContent || "";
    link.textContent = restoredLabel;
    link.classList.remove("muted");
    link.setAttribute("aria-disabled", "false");
    delete link.dataset.loading;
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
      link.href = record._clickUrl ? record._clickUrl : "#";
      link.ariaDisabled = String(record.masar_status === "missing" || !record._clickUrl);
      const linkLabel = record.masar_status === "missing"
        ? Strings.STATUS_MISSING
        : (record._clickUrl ? Strings.VIEW_DETAILS : Strings.DETAILS_UNAVAILABLE);
      link.textContent = linkLabel;
      link.addEventListener("click", async (event) => {
        event.preventDefault();
        if (link.dataset.loading === "true") {
          return;
        }
        if (record.masar_status === "missing" || !record._clickUrl) {
          showToast(
            record.masar_status === "missing" ? Strings.DETAILS_RECORD_MISSING : Strings.DETAILS_UNAVAILABLE,
            { tone: "error" },
          );
          return;
        }
        setDetailLinkLoadingState(link, true, linkLabel);
        try {
          await handleCardClick({
            clickUrl: record._clickUrl,
            uploadId: record.upload_id,
            detailsContext: {
              submission_entity_id: record.submission_entity_id || null,
              submission_entity_type_id: record.submission_entity_type_id || null,
              submission_contract_id: record.submission_contract_id || null,
              submission_contract_name: record.submission_contract_name || null,
              submission_contract_name_ar: record.submission_contract_name_ar || null,
              submission_contract_name_en: record.submission_contract_name_en || null,
              submission_contract_number: record.submission_contract_number || null,
              submission_contract_status: record.submission_contract_status ?? null,
              submission_uo_subscription_status_id: record.submission_uo_subscription_status_id ?? null,
            },
          onOpenStart: (message) => showToast(message, { durationMs: 15000 }),
          onMissingRecord: async (message) => {
              state.activeTab = "failed";
              await loadMainWorkspace({ showLoading: false, fetchRecords: true });
              showToast(message, { tone: "error", durationMs: 5000 });
          },
          onInaccessible: (message) => showToast(message, { tone: "error" }),
          onOpenFailed: (message) => showToast(message, { tone: "error" }),
        });
        } finally {
          setDetailLinkLoadingState(link, false, linkLabel);
        }
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
    const pending = await ContextChange.hasContextChangePending();
    const text = $("context-change-text", doc);
    if (!pending || state.hiddenContextBanner) {
      banner.classList.add("hidden");
      return;
    }
    text.textContent = Strings.CTX_CHANGE_ENTITY;
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
    const cache = state.tabCache[tabName];
    if (tabName !== "inProgress" && cache && !cache.loaded) {
      void loadTabPage(tabName, { silent: true }).then(() => {
        if (state.lastLocalData && state.lastSessionData) {
          renderWorkspaceFromCache(state.lastLocalData, state.lastSessionData);
        }
      });
      return;
    }
    if (tabName !== "inProgress" && cache && cache.loaded && (Date.now() - cache.lastLoadedAt) > 15000) {
      void loadTabPage(tabName, { silent: true }).then(() => {
        if (state.lastLocalData && state.lastSessionData) {
          renderWorkspaceFromCache(state.lastLocalData, state.lastSessionData);
        }
      });
    }
  }

  function applySummaryContext(localData, doc = document) {
    $("ctx-entity", doc).textContent =
      localData.masar_user_name || localData.masar_entity_id || "—";
    $("ctx-contract", doc).textContent =
      localData.masar_contract_name_ar ||
      localData.masar_contract_name_en ||
      localData.masar_contract_id ||
      "—";
    const groupValue = $("ctx-group", doc);
    if (groupValue) {
      groupValue.textContent = localData.masar_group_name || localData.masar_group_id || "—";
    }
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
    } else if (localData.masar_contract_state === "inactive") {
      pill.textContent = Strings.CONTRACT_INACTIVE;
      pill.dataset.tone = "red";
      pill.classList.remove("hidden");
    } else if (localData.masar_contract_state === "unknown") {
      pill.classList.add("hidden");
      pill.textContent = "";
      pill.dataset.tone = "";
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

  function buildOptimisticCounts(serverCounts, batchState, activeSubmitId = null) {
    const normalized = QueueFilter.normalizeBatchState(batchState, activeSubmitId);
    const inProgressCount = normalized.inProgressIds.size;
    const submittedCount = normalized.submittedIds.size;
    const failedCount = normalized.failedIds.size;
    return {
      pending: Math.max((serverCounts?.pending || 0) - inProgressCount - submittedCount - failedCount, 0),
      inProgress: inProgressCount,
      submitted: (serverCounts?.submitted || 0) + submittedCount,
      failed: (serverCounts?.failed || 0) + failedCount,
    };
  }

  function mergeTabPageState(cache, responseData, { append = false, loadedAt = Date.now() } = {}) {
    const incomingItems = Array.isArray(responseData?.items) ? responseData.items : [];
    const mergedItems = append ? [...(cache.items || []), ...incomingItems] : incomingItems;
    return {
      ...cache,
      items: mergedItems,
      total: responseData?.total || 0,
      offset: (responseData?.offset || 0) + incomingItems.length,
      hasMore: Boolean(responseData?.has_more),
      loaded: true,
      loading: false,
      error: null,
      lastLoadedAt: loadedAt,
    };
  }

  function buildRenderableServerSections(caches, lastSubmitResult = null) {
    const sections = QueueFilter.filterServerSections(caches);
    if (!lastSubmitResult?.upload_id) {
      return sections;
    }
    const uploadId = lastSubmitResult.upload_id;
    let sourceRecord = null;
    for (const key of ["pending", "submitted", "failed"]) {
      const records = Array.isArray(sections[key]) ? sections[key] : [];
      const match = records.find((record) => record.upload_id === uploadId) || null;
      if (match && !sourceRecord) {
        sourceRecord = match;
      }
      sections[key] = records.filter((record) => record.upload_id !== uploadId);
    }
    if (!sourceRecord) {
      return sections;
    }
    const updatedRecord = applyLastSubmitResult([sourceRecord], lastSubmitResult)[0] || sourceRecord;
    if (lastSubmitResult.status === "submitted") {
      sections.submitted.push(updatedRecord);
    } else if (lastSubmitResult.status === "failed" || lastSubmitResult.status === "missing") {
      sections.failed.push(updatedRecord);
    } else {
      sections.pending.push(updatedRecord);
    }
    return sections;
  }

  function buildBatchBannerState(sessionData) {
    const normalized = QueueFilter.normalizeBatchState(
      sessionData?.submission_batch || [],
      sessionData?.active_submit_id || null,
    );
    const batch = sessionData?.submission_batch;
    const submittedCount = Array.isArray(batch?.submitted_ids) ? batch.submitted_ids.length : 0;
    const activeCount = normalized.activeId ? 1 : 0;
    const queuedCount = Math.max(normalized.inProgressIds.size - activeCount, 0);
    const total = typeof batch?.source_total === "number"
      ? batch.source_total
      : submittedCount + normalized.inProgressIds.size;
    const blockedReason = batch && typeof batch === "object" && !Array.isArray(batch)
      ? batch.blocked_reason || null
      : null;
    return {
      visible: normalized.inProgressIds.size > 0 || Boolean(blockedReason),
      title: Strings.PROGRESS_BANNER_TITLE,
      summary: Strings.PROGRESS_BANNER_SUMMARY(submittedCount, total || submittedCount),
      detail: Strings.PROGRESS_BANNER_DETAIL(activeCount, queuedCount),
      blockedReason,
    };
  }

  function renderSubmissionBanner(sessionData, doc = document) {
    const banner = $("submission-progress-banner", doc);
    if (!banner) {
      return;
    }
    const stateForBanner = buildBatchBannerState(sessionData);
    if (!stateForBanner.visible) {
      banner.classList.add("hidden");
      return;
    }
    $("submission-progress-title", doc).textContent = stateForBanner.title;
    $("submission-progress-summary", doc).textContent = stateForBanner.summary;
    $("submission-progress-detail", doc).textContent = stateForBanner.detail;
    $("submission-resume-btn", doc).classList.toggle("hidden", !stateForBanner.blockedReason);
    banner.dataset.blocked = stateForBanner.blockedReason ? "true" : "false";
    banner.classList.remove("hidden");
  }

  function mapTabToSection(tabName) {
    return tabName === "inProgress" ? "pending" : tabName;
  }

  async function loadCounts({ silent = false } = {}) {
    state.countsState.loading = true;
    const response = await sendMsg({ type: "FETCH_RECORD_COUNTS" }, { timeoutMs: 10000 });
    state.countsState.loading = false;
    if (!response?.ok) {
      state.countsState.stale = true;
      if (!silent && state.countsState.server) {
        showToast(Strings.ERR_UNEXPECTED, { tone: "error" });
      }
      return response;
    }
    state.countsState.server = response.data;
    state.countsState.stale = false;
    return response;
  }

  async function loadTabPage(tabName, { append = false, silent = false } = {}) {
    if (tabName === "inProgress") {
      return { ok: true, data: state.tabCache.inProgress };
    }
    const cache = state.tabCache[tabName];
    if (!cache) {
      return { ok: false, error: Strings.ERR_UNEXPECTED };
    }
    cache.loading = true;
    cache.error = null;
    const response = await sendMsg(
      {
        type: "FETCH_RECORD_PAGE",
        section: mapTabToSection(tabName),
        limit: 50,
        offset: append ? cache.offset : 0,
      },
      { timeoutMs: 10000 },
    );
    cache.loading = false;
    if (!response?.ok) {
      cache.error = response?.error || Strings.ERR_UNEXPECTED;
      if (!silent) {
        showToast(Strings.LIST_REFRESH_FAILED || Strings.ERR_UNEXPECTED, { tone: "error" });
      }
      return response;
    }
    state.tabCache[tabName] = mergeTabPageState(cache, response.data, {
      append,
      loadedAt: Date.now(),
    });
    return response;
  }

  function renderWorkspaceFromCache(localData, sessionData) {
    state.lastLocalData = localData;
    state.lastSessionData = sessionData;
    const activeSubmitId = sessionData.active_submit_id || null;
    const serverSections = buildRenderableServerSections({
      pending: state.tabCache.pending.items,
      submitted: state.tabCache.submitted.items,
      failed: state.tabCache.failed.items,
    }, sessionData.last_submit_result || null);
    const sections = QueueFilter.mergeOptimisticSections({
      serverSections,
      batchState: sessionData.submission_batch || [],
      activeSubmitId,
    });
    const pendingVisible = sections.pending.filter((record) => !state.skippedIds.has(record.upload_id));
    const canSubmit =
      Boolean(localData.masar_entity_id)
      && localData.masar_contract_state !== "expired"
      && localData.masar_contract_state !== "inactive";
    const counts = state.countsState.server
      ? buildOptimisticCounts(state.countsState.server, sessionData.submission_batch || [], activeSubmitId)
      : {
          pending: pendingVisible.length,
          inProgress: sections.inProgress.length,
          submitted: sections.submitted.length,
          failed: sections.failed.length,
        };

    state.sectionData = sections;
    applySummaryContext(localData);
    renderSubmissionBanner(sessionData);
    renderHomeSummary(document, {
      pendingCount: counts.pending,
      failedCount: counts.failed,
    });
    $("tab-count-pending").textContent = String(counts.pending);
    $("tab-count-in-progress").textContent = String(counts.inProgress);
    $("tab-count-submitted").textContent = String(counts.submitted);
    $("tab-count-failed").textContent = String(counts.failed);

    const pendingRecords = pendingVisible.map((record) => ({
      ...record,
      _submitDisabled: !canSubmit,
      _onSubmit: () => submitSingle(record),
      _onSkip: () => {
        state.skippedIds.add(record.upload_id);
        renderWorkspaceFromCache(localData, sessionData);
      },
    }));
    const inProgressRecords = sections.inProgress.map((record) => ({
      ...record,
      _inProgressState: record.upload_id === activeSubmitId ? "active" : "queued",
    }));
    const submittedRecords = sections.submitted.map((record) => ({
      ...record,
      _clickUrl: record.masar_status === "missing" ? null : getClickUrl(record),
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
    renderLoadMoreControls();
    $("submit-all-btn").disabled = !canSubmit || pendingRecords.length === 0;
    $("submit-all-btn").onclick = () => void submitBatch(pendingRecords.map((record) => record.upload_id));
  }

  function renderLoadMoreControls(doc = document) {
    const mappings = [
      ["pending", "pending-load-more"],
      ["submitted", "submitted-load-more"],
      ["failed", "failed-load-more"],
    ];
    for (const [tabName, buttonId] of mappings) {
      const button = $(buttonId, doc);
      const cache = state.tabCache[tabName];
      if (!button || !cache) {
        continue;
      }
      button.classList.toggle("hidden", !cache.hasMore);
      button.disabled = cache.loading;
      button.onclick = cache.hasMore
        ? () => void loadTabPage(tabName, { append: true }).then(() => {
          if (state.lastLocalData && state.lastSessionData) {
            renderWorkspaceFromCache(state.lastLocalData, state.lastSessionData);
          }
        })
        : null;
    }
  }

  async function getContractsForUi({ forceRefresh = false } = {}) {
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
    return contracts;
  }

  async function resolveContextAfterContracts(localData, contracts) {
    const activeUiContext = ContextChange.normalizeActiveUiContext(
      localData.active_ui_context || (await ContextChange.getActiveUiContext()),
    );
    const preferredContractId = localData.masar_contract_id || activeUiContext.contract_id || null;
    const resolution = ContextChange.resolveContractContext(activeUiContext, contracts, preferredContractId);

    let nextContext = resolution.nextContext;
    if (resolution.mode === "selected" && resolution.selectedContract) {
      const selectedContractId = String(resolution.selectedContract.contractId);
      const groupResponse = await sendMsg({ type: "FETCH_GROUPS", contractId: selectedContractId });
      const validGroups = ContextChange.filterSelectableGroups(groupResponse?.data?.response?.data?.content || []);
      nextContext = ContextChange.buildExplicitContractSelectionContext(
        {
          ...nextContext,
          available_contracts: resolution.selectableContracts,
        },
        resolution.selectedContract,
        validGroups,
      );
      nextContext = {
        ...nextContext,
        available_contracts: resolution.selectableContracts,
      };
    }

    await ContextChange.setActiveUiContext(nextContext);

    return {
      ...localData,
      masar_contract_id: nextContext.contract_id,
      masar_contract_name_ar: nextContext.contract_name_ar,
      masar_contract_name_en: nextContext.contract_name_en,
      masar_contract_state: nextContext.contract_state,
      masar_group_id: nextContext.group_id,
      masar_group_name: nextContext.group_name,
      masar_group_number: nextContext.group_number,
      active_ui_context: nextContext,
    };
  }

  function buildContractPickerState(contracts, currentContractId) {
    const resolution = ContextChange.resolveContractContext(
      ContextChange.getDefaultActiveUiContext(),
      contracts,
      currentContractId,
    );
    const selectableContracts = resolution.selectableContracts;
    if (selectableContracts.length === 0) {
      return {
        resolution,
        selectableContracts,
        showDropdown: false,
        emptyMessage: Strings.CONTRACT_NONE_AVAILABLE_CURRENT_ACCOUNT,
      };
    }
    return {
      resolution,
      selectableContracts,
      showDropdown: selectableContracts.length > 1,
      emptyMessage: "",
    };
  }

  async function populateContractDropdown(currentContractId, doc = document, { forceRefresh = false } = {}) {
    const container = $("contract-dropdown-container", doc);
    const select = $("contract-select", doc);
    const emptyState = $("contract-empty-state", doc);
    select.innerHTML = "";
    select.append(new Option(Strings.CONTRACT_SELECT_PLACEHOLDER, ""));
    emptyState.textContent = "";
    emptyState.classList.add("hidden");
    select.classList.remove("hidden");
    try {
      const contracts = await getContractsForUi({ forceRefresh });
      const pickerState = buildContractPickerState(contracts, currentContractId);
      if (pickerState.selectableContracts.length === 0) {
        container.classList.remove("hidden");
        select.disabled = true;
        select.classList.add("hidden");
        emptyState.textContent = pickerState.emptyMessage;
        emptyState.classList.remove("hidden");
        return;
      }
      pickerState.selectableContracts.forEach((contract) => {
        const option = new Option(
          contract.companyNameAr || contract.companyNameEn || String(contract.contractId),
          String(contract.contractId),
        );
        select.append(option);
      });
      select.disabled = false;
      container.classList.toggle("hidden", !pickerState.showDropdown);
      if (pickerState.resolution.selectedContract) {
        select.value = String(pickerState.resolution.selectedContract.contractId);
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
          submission_entity_id: result.submission_entity_id || record.submission_entity_id || null,
          submission_entity_type_id: result.submission_entity_type_id || record.submission_entity_type_id || null,
          submission_entity_name: result.submission_entity_name || record.submission_entity_name || null,
          submission_contract_id: result.submission_contract_id || record.submission_contract_id || null,
          submission_contract_name: result.submission_contract_name || record.submission_contract_name || null,
          submission_contract_name_ar:
            result.submission_contract_name_ar || record.submission_contract_name_ar || null,
          submission_contract_name_en:
            result.submission_contract_name_en || record.submission_contract_name_en || null,
          submission_contract_number:
            result.submission_contract_number || record.submission_contract_number || null,
          submission_contract_status:
            typeof result.submission_contract_status === "boolean"
              ? result.submission_contract_status
              : record.submission_contract_status ?? null,
          submission_uo_subscription_status_id:
            typeof result.submission_uo_subscription_status_id === "number"
              ? result.submission_uo_subscription_status_id
              : record.submission_uo_subscription_status_id ?? null,
          submission_group_id: result.submission_group_id || record.submission_group_id || null,
          submission_group_name: result.submission_group_name || record.submission_group_name || null,
          submission_group_number: result.submission_group_number || record.submission_group_number || null,
        };
      }
      if (result.status === "missing") {
        return {
          ...record,
          masar_status: "missing",
        };
      }
      if (result.status === "failed") {
        return {
          ...record,
          masar_status: "failed",
          failure_reason_code: result.failure_reason_code || record.failure_reason_code || null,
          failure_reason_text: result.failure_reason_text || record.failure_reason_text || null,
        };
      }
      return record;
    });
  }

  async function submitSingle(record) {
    if (!(await ensureActionContext("submit"))) {
      return;
    }
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
    if (!(await ensureActionContext("batch"))) {
      return;
    }
    const discovery = await sendMsg(
      { type: "FETCH_SUBMIT_ELIGIBLE_IDS", section: "pending", limit: 100, offset: 0 },
      { timeoutMs: 10000 },
    );
    if (!discovery?.ok) {
      showToast(Strings.ERR_UNEXPECTED, { tone: "error" });
      return;
    }
    const discoveredIds = Array.isArray(discovery.data?.items)
      ? discovery.data.items.map((item) => item.upload_id).filter(Boolean)
      : [];
    const sourceTotal = discovery.data?.total || discoveredIds.length;
    if (!discoveredIds.length) {
      return;
    }
    const confirmed = window.confirm(Strings.SUBMIT_ALL_CONFIRM(sourceTotal));
    if (!confirmed) {
      return;
    }
    const response = await sendMsg({
      type: "SUBMIT_BATCH",
      uploadIds: discoveredIds,
      sourceTotal,
      nextOffset: discoveredIds.length,
    }, { timeoutMs: 30000 });
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
      let [localData, sessionData, countsResponse, pageResponse] = await Promise.all([
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
          "active_ui_context",
        ]),
        sessionGet(["submission_batch", "active_submit_id", "last_submit_result"]),
        fetchRecords ? loadCounts({ silent: true }) : Promise.resolve({ ok: true, data: state.countsState.server }),
        fetchRecords ? loadTabPage(state.activeTab, { silent: true }) : Promise.resolve({ ok: true }),
      ]);
      const contracts = await getContractsForUi({ forceRefresh: refreshContracts });
      localData = await resolveContextAfterContracts(localData, contracts);

      if (!pageResponse?.ok && !state.tabCache[state.activeTab]?.loaded) {
        const failure = Failure.classifyFailure(pageResponse);
        if (failure.type === "relink") {
          await showRelinkRequired();
          return;
        }
        showError(pageResponse?.error || Strings.ERR_UNEXPECTED);
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

      if (!countsResponse?.ok) {
        state.countsState.stale = true;
      }
      renderWorkspaceFromCache(localData, sessionData);
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

  function decideBootstrapAction({ hasApiToken, hasEntityAfterSync }) {
    if (!hasApiToken) {
      return "setup";
    }
    if (!hasEntityAfterSync) {
      return "activate";
    }
    return "main";
  }

  async function init() {
    showScreen("loading");
    const stored = await localGet([
      "api_token",
      "masar_entity_id",
      "agency_email",
      "agency_phone",
      "agency_phone_country_code",
    ]);
    if (decideBootstrapAction({ hasApiToken: Boolean(stored.api_token), hasEntityAfterSync: false }) === "setup") {
      showSetupError("");
      showScreen("setup");
      return;
    }

    await sendMsg({ type: "SYNC_SESSION" });
    const synced = await localGet(["masar_entity_id"]);
    if (decideBootstrapAction({ hasApiToken: true, hasEntityAfterSync: Boolean(synced.masar_entity_id) }) === "activate") {
      showScreen("activate");
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

  async function handleResumeBatchResponse({ response, onReload, onUnavailable }) {
    if (response?.ok) {
      await onReload();
      return true;
    }
    if (response?.errorCode === "submission-batch-missing") {
      await onUnavailable();
      return false;
    }
    await onReload();
    return false;
  }

  async function handleContractSelectionChange({ value, writeSelection, reloadWorkspace }) {
    await writeSelection({ masar_contract_id: value });
    await reloadWorkspace();
  }

  async function ensureActionContext(actionType) {
    const localData = await localGet(["active_ui_context", "masar_contract_id", "masar_group_id"]);
    const requirement = ensureActionContextState({
      activeUiContext: localData.active_ui_context,
      selectedContractId: localData.masar_contract_id || null,
    });
    if (requirement.ok) {
      return true;
    }
    if (requirement.reason === "contract" || requirement.reason === "contract-inactive") {
      await populateContractDropdown(localData.masar_contract_id || null, document, { forceRefresh: true });
      showScreen("main");
      activateTab(state.activeTab);
      showToast(
        requirement.reason === "contract-inactive"
          ? Strings.CONTRACT_INACTIVE_ACTION_REQUIRED
          : Strings.CONTRACT_ACTION_REQUIRED,
        { tone: "error" },
      );
      $("contract-select")?.focus?.();
      return false;
    }
    return true;
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
    $("btn-refresh-context").addEventListener("click", async () => {
      await sendMsg({ type: "SYNC_SESSION" });
      await init();
    });
    $("submission-refresh-btn")?.addEventListener("click", async () => {
      await loadMainWorkspace({ showLoading: false, fetchRecords: true });
    });
    $("submission-resume-btn")?.addEventListener("click", async () => {
      const response = await sendMsg({ type: "SUBMIT_BATCH", uploadIds: [] }, { timeoutMs: 30000 });
      await handleResumeBatchResponse({
        response,
        onReload: () => loadMainWorkspace({ showLoading: false, fetchRecords: false }),
        onUnavailable: async () => {
          showToast(Strings.SUBMIT_RESUME_UNAVAILABLE, { tone: "error" });
          await loadMainWorkspace({ showLoading: false, fetchRecords: false });
        },
      });
    });
    $("ctx-change-confirm").addEventListener("click", async () => {
      state.hiddenContextBanner = false;
      await sendMsg({ type: "SYNC_SESSION" });
      await loadMainWorkspace({ showLoading: false, fetchRecords: true, refreshContracts: true });
    });
    $("ctx-change-defer").addEventListener("click", async () => {
      state.hiddenContextBanner = true;
      await initContextChangeBanner();
    });
    $("contract-select").addEventListener("change", async (event) => {
      if (!event.target.value) {
        return;
      }
      const contracts = Array.isArray(state.contractsCache) ? state.contractsCache : await ContractSelect.fetchContracts();
      const selectedContract = contracts.find(
        (contract) => String(contract.contractId) === String(event.target.value),
      );
      await localSet({ masar_contract_id: event.target.value });
      const groupResponse = await sendMsg({ type: "FETCH_GROUPS", contractId: event.target.value });
      const validGroups = ContextChange.filterSelectableGroups(groupResponse?.data?.response?.data?.content || []);
      const activeUiContext = await ContextChange.getActiveUiContext();
      await ContextChange.setActiveUiContext(
        ContextChange.buildExplicitContractSelectionContext(activeUiContext, selectedContract, validGroups),
      );
      await handleContractSelectionChange({
        value: event.target.value,
        writeSelection: localSet,
        reloadWorkspace: () => loadMainWorkspace({ showLoading: false, fetchRecords: true }),
      });
    });
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        activateTab(tab.dataset.tab);
      });
    });
  }

  return {
    bootstrap,
    buildDisplayName,
    buildBatchBannerState,
    buildOptimisticCounts,
    buildRenderableServerSections,
    ensureActionContextState,
    getRecordNote,
    getScreenTheme,
    handleCardClick,
    handleContractSelectionChange,
    decideBootstrapAction,
    getSubmissionContextMismatchToast,
    handleResumeBatchResponse,
    handleSubmitResponse,
    initContextChangeBanner,
    mergeTabPageState,
    renderHomeSummary,
    renderPendingCard,
    buildContractPickerState,
    setDetailLinkLoadingState,
    getSubmissionContextMismatch,
    showToast,
  };
});
