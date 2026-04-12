(function (root, factory) {
  const api = factory({
    Auth: root.MasarAuth || require("./auth.js"),
    ContractSelect: root.MasarContractSelect || require("./contract-select.js"),
    ContextChange: root.MasarContextChange || require("./context-change.js"),
    Failure: root.MasarPopupFailure || require("./popup-failure.js"),
    QueueFilter: root.MasarQueueFilter || require("./queue-filter.js"),
    Status: root.MasarStatus || require("./status.js"),
    Strings: root.MasarStrings || require("./strings.js"),
    TabDataStore: root.MasarTabDataStore || require("./tab-data-store.js"),
    TabFetchCoordinator: root.MasarTabFetchCoordinator || require("./tab-fetch-coordinator.js"),
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
  TabDataStore,
  TabFetchCoordinator,
  apiBaseUrl,
}) {
  const SERVER_TABS = ["pending", "submitted", "failed"];

  const state = {
    currentScreen: null,
    activeTab: "pending",
    selectedUploadIds: new Set(),
    sectionData: null,
    tabDisplay: TabDataStore.create(),
    tabCoordinator: TabFetchCoordinator.create(),
    lastLocalData: null,
    lastSessionData: null,
    workspaceLoadId: 0,
    contractsCache: null,
    toastTimer: null,
    renderTimer: null,
    canSubmitSelection: false,
    submitActionBlockedReason: null,
  };
  const PRE_RELEASE_SHOW_RAW_FAILURES = true;

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
    state.currentScreen = name;
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
      $("help-support-link", doc).textContent = Strings.HELP_LINK_LABEL;
      $("help-support-link", doc).title = Strings.HELP_LINK_TITLE;
      $("help-support-link", doc).ariaLabel = Strings.HELP_LINK_LABEL;
      $("help-support-link", doc).href = Strings.HELP_LINK_URL;
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
    setText("home-pending-label", Strings.HOME_PENDING_LABEL);

    setText("home-submitted-label", Strings.HOME_SUBMITTED_LABEL);
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
    setText("submission-progress-title", Strings.PROGRESS_BANNER_TITLE);
    setText("submission-refresh-btn", Strings.ACTION_REFRESH);
    setText("submission-resume-btn", Strings.ACTION_RESUME);
    setText("pending-load-more", Strings.ACTION_LOAD_MORE);
    setText("submitted-load-more", Strings.ACTION_LOAD_MORE);
    setText("failed-load-more", Strings.ACTION_LOAD_MORE);
    setText("mark-all-btn", Strings.ACTION_MARK_ALL_SELECTABLE);
    setText("selected-action-submit-btn", Strings.ACTION_SUBMIT_SELECTED);
    setText("selected-action-archive-btn", Strings.ACTION_ARCHIVE_SELECTED);
    setText("workspace-empty-note", Strings.SECTION_EMPTY_PENDING);
    setText("settings-kicker", Strings.SETTINGS_KICKER);
    setText("settings-title", Strings.SETTINGS_TITLE);
    setText("settings-subtitle", Strings.SETTINGS_SUBTITLE);
    setText("settings-contact-hint-title", Strings.SETTINGS_CONTACT_HINT_TITLE);
    setText("settings-contact-hint-body", Strings.SETTINGS_CONTACT_HINT_BODY);
    setText("btn-back", Strings.ACTION_BACK);
    setText("settings-email-label", Strings.SETTINGS_EMAIL_LABEL);
    setPlaceholder("settings-email", Strings.SETTINGS_EMAIL_PLACEHOLDER);
    setText("settings-phone-cc-label", Strings.SETTINGS_PHONE_CC_LABEL);
    setPlaceholder("settings-phone-cc", Strings.SETTINGS_PHONE_CC_PLACEHOLDER);
    setText("settings-phone-label", Strings.SETTINGS_PHONE_LABEL);
    setPlaceholder("settings-phone", Strings.SETTINGS_PHONE_PLACEHOLDER);
    setText("btn-save-settings", Strings.SETTINGS_SAVE);
    setText("btn-reset-token", Strings.SETTINGS_RESET);
    setText("contact-defaults-nudge-text", Strings.CONTACT_DEFAULTS_NUDGE);
    setText("contact-defaults-nudge-btn", Strings.CONTACT_DEFAULTS_NUDGE_ACTION);
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

  function reconcileSelectedUploadIds(selectedIds, selectableIds) {
    const next = new Set();
    for (const uploadId of selectedIds || []) {
      if (selectableIds?.has(uploadId)) {
        next.add(uploadId);
      }
    }
    return next;
  }

  function parseTimestamp(value) {
    if (typeof value !== "string" || !value) {
      return 0;
    }
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function compareByCreatedAtDesc(left, right) {
    const leftTs = parseTimestamp(left?.created_at);
    const rightTs = parseTimestamp(right?.created_at);
    if (leftTs !== rightTs) {
      return rightTs - leftTs;
    }
    return Number(right?.upload_id || 0) - Number(left?.upload_id || 0);
  }

  function sortInProgressRecords(records, sessionData) {
    const batch = sessionData?.submit_batch;
    const queue = Array.isArray(batch?.queue) ? batch.queue : [];
    const queueOrder = new Map(
      queue
        .map((uploadId, index) => [Number(uploadId), index])
        .filter(([uploadId]) => Number.isFinite(uploadId) && uploadId > 0),
    );
    const candidateActive = batch?.active_id ?? sessionData?.active_submit_id ?? null;
    const parsedActiveId = Number(candidateActive);
    const activeId = Number.isFinite(parsedActiveId) && parsedActiveId > 0 ? parsedActiveId : null;

    return [...(Array.isArray(records) ? records : [])].sort((left, right) => {
      const leftId = Number(left?.upload_id || 0);
      const rightId = Number(right?.upload_id || 0);
      const leftIsActive = activeId !== null && leftId === activeId;
      const rightIsActive = activeId !== null && rightId === activeId;
      if (leftIsActive !== rightIsActive) {
        return leftIsActive ? -1 : 1;
      }
      const leftIndex = queueOrder.has(leftId) ? queueOrder.get(leftId) : Number.POSITIVE_INFINITY;
      const rightIndex = queueOrder.has(rightId) ? queueOrder.get(rightId) : Number.POSITIVE_INFINITY;
      if (leftIndex !== rightIndex) {
        return leftIndex - rightIndex;
      }
      return compareByCreatedAtDesc(left, right);
    });
  }

  function sortSectionsForRender({ sections, sessionData }) {
    const source = sections || {};
    return {
      pending: source.pending || [],
      inProgress: sortInProgressRecords(source.inProgress || [], sessionData || {}),
      submitted: source.submitted || [],
      failed: source.failed || [],
    };
  }

  function isBatchCurrentlyRunning(sessionData) {
    const submitRunning = QueueFilter.normalizeBatchState(
      sessionData?.submit_batch || [],
      sessionData?.active_submit_id || null,
    ).inProgressIds.size > 0;
    const archiveRunning = QueueFilter.normalizeBatchState(
      sessionData?.archive_batch || [],
      sessionData?.active_archive_id || null,
    ).inProgressIds.size > 0;
    return submitRunning || archiveRunning;
  }

  function buildSubmitSelectionActionState({
    selectedCount,
    isBatchRunning,
    canSubmit = true,
  }) {
    const loading = isBatchRunning;
    const disabled = loading || selectedCount === 0;
    return {
      hidden: false,
      disabled,
      loading,
      submitDisabled: disabled || !canSubmit,
      label: Strings.ACTION_SELECTED_COUNT(selectedCount),
    };
  }

  function getSubmitActionAvailability(localData = {}) {
    const requirement = ensureActionContextState({
      activeUiContext: localData.active_ui_context,
      selectedContractId: localData.masar_contract_id || null,
    });
    if (requirement.ok) {
      return { canSubmit: true, reason: null };
    }
    if (requirement.reason === "contract-inactive") {
      return { canSubmit: false, reason: Strings.CONTRACT_INACTIVE_ACTION_REQUIRED };
    }
    return { canSubmit: false, reason: Strings.CONTRACT_ACTION_REQUIRED };
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
    if (inProgress) {
      return "olive";
    }
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
    if (review_status === "needs_review") {
      return "amber";
    }
    return "green";
  }

  function getRecordVisualState(record) {
    if (record._inProgressState) {
      return "processing";
    }
    if (record.upload_status === "failed" || record.masar_status === "failed") {
      return "failed";
    }
    if (record.masar_status === "missing") {
      return "failed";
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
    if (record._inProgressState) {
      return "";
    }
    if (record.review_status === "needs_review") {
      return Strings.REVIEW_SUMMARY;
    }
    if (typeof record.failure_reason_text === "string" && record.failure_reason_text.trim()) {
      if (record._section === "failed" && PRE_RELEASE_SHOW_RAW_FAILURES) {
        return record.failure_reason_text.trim();
      }
      return record._section === "failed" ? Strings.STATUS_FAILED : Strings.ERR_UNEXPECTED;
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
    return "";
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

  async function loadServerCounts() {
    const response = await sendMsg({ type: "FETCH_RECORD_COUNTS" }, { timeoutMs: 5000 });
    if (!response?.ok) {
      return null;
    }
    return response.data;
  }

  function renderMetrics(counts, doc = document) {
    if (!counts) return;
    $("metric-pending", doc).textContent = String(counts.pending || 0);

    $("metric-submitted", doc).textContent = String(counts.submitted || 0);
    const failedValue = counts.failed || 0;
    const failedEl = $("metric-failed", doc);
    failedEl.textContent = String(failedValue);
    failedEl.dataset.tone = failedValue > 0 ? "danger" : "normal";
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

  function renderPendingCard(doc, record) {
    const article = doc.createElement("article");
    article.className = `record rich ${getRecordVisualState(record)}`;
    article.dataset.uploadId = String(record.upload_id);
    const isSelectable = record._section === "pending" || record._section === "failed";
    article.classList.toggle("is-selectable", isSelectable);
    article.classList.toggle("is-selected", isSelectable && Boolean(record._selected));
    if (isSelectable) {
      article.tabIndex = 0;
      article.setAttribute("role", "button");
      article.setAttribute("aria-pressed", record._selected ? "true" : "false");
    }

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

    const reviewText = getRecordNote(record);
    const review = doc.createElement("div");
    review.className = "record-review";
    review.textContent = reviewText;

    const footer = doc.createElement("div");
    footer.className = "record-footer";
    const actions = doc.createElement("div");
    actions.className = "record-actions";

    const updateSelectionVisualState = () => {
      const selected = state.selectedUploadIds.has(record.upload_id);
      article.classList.toggle("is-selected", isSelectable && selected);
      if (isSelectable) {
        article.setAttribute("aria-pressed", selected ? "true" : "false");
      }
    };
    const updateSelectionActionState = () => {
      updateSubmitSelectionAction({
        isBatchRunning: isBatchCurrentlyRunning(state.lastSessionData),
        canSubmit: state.canSubmitSelection,
      });
    };
    if (isSelectable) {
      const toggleSelection = () => {
        const next = new Set(state.selectedUploadIds);
        if (next.has(record.upload_id)) {
          next.delete(record.upload_id);
        } else {
          next.add(record.upload_id);
        }
        state.selectedUploadIds = next;
        updateSelectionVisualState();
        updateSelectionActionState();
      };
      article.addEventListener("click", (event) => {
        if (event.target.closest("a,button")) {
          return;
        }
        toggleSelection();
      });
      article.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") {
          return;
        }
        event.preventDefault();
        toggleSelection();
      });
      updateSelectionVisualState();
    }

    if (record._section === "submitted") {
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
    if (reviewText) {
      body.append(header, review, footer);
    } else {
      body.append(header, footer);
    }
    article.append(createPassportThumb(doc, record), body);
    return article;
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

  function getSectionEmptyNote(sectionName, sectionData = null) {
    const records = Array.isArray(sectionData?.[sectionName]) ? sectionData[sectionName] : [];
    if (records.length > 0) {
      return "";
    }
    return {
      pending: Strings.SECTION_EMPTY_PENDING,
      inProgress: Strings.SECTION_EMPTY_IN_PROGRESS,
      submitted: Strings.SECTION_EMPTY_SUBMITTED,
      failed: Strings.SECTION_EMPTY_FAILED,
    }[sectionName] || Strings.SECTION_EMPTY_PENDING;
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
      submitAll.classList.remove("hidden");
    }
    if (!emptyHint) {
      return;
    }
    emptyHint.textContent = getSectionEmptyNote(sectionName, state.sectionData);
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
    if (tabName !== "inProgress" && TabFetchCoordinator.isDirty(state.tabCoordinator, tabName)) {
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
      sessionData?.submit_batch || [],
      sessionData?.active_submit_id || null,
    );
    const batch = sessionData?.submit_batch;
    const results = batch && typeof batch.results === "object" && !Array.isArray(batch.results)
      ? batch.results
      : {};
    const statuses = Object.values(results);
    const submittedCount = statuses.filter((status) => status === "submitted").length;
    const failedCount = statuses.filter((status) => status === "failed" || status === "missing").length;
    const activeCount = normalized.activeId ? 1 : 0;
    const queueSize = Array.isArray(batch?.queue) ? batch.queue.length : 0;
    const queuedCount = Math.max(queueSize - submittedCount - failedCount - activeCount, 0);
    const total = queueSize || submittedCount + failedCount + normalized.inProgressIds.size;
    const blockedReason = batch && typeof batch === "object" && !Array.isArray(batch)
      ? batch.blocked_reason || null
      : null;
    return {
      visible: normalized.inProgressIds.size > 0 || Boolean(blockedReason),
      title: Strings.PROGRESS_BANNER_TITLE,
      summary: Strings.PROGRESS_BANNER_SUMMARY(submittedCount, total || submittedCount),
      detail: Strings.PROGRESS_BANNER_DETAIL(activeCount, queuedCount, failedCount),
      blockedReason,
    };
  }

  function renderContactDefaultsNudge(localData) {
    const nudge = $("contact-defaults-nudge");
    if (!nudge) {
      return;
    }
    const missing = !localData.agency_email && !localData.agency_phone;
    nudge.classList.toggle("hidden", !missing);
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


  async function loadTabPage(tabName, { silent = false } = {}) {
    if (tabName === "inProgress") {
      return { ok: true };
    }
    const { nextCoordinator, requestId } = TabFetchCoordinator.beginFetch(state.tabCoordinator, tabName);
    state.tabCoordinator = nextCoordinator;
    const response = await sendMsg(
      {
        type: "FETCH_RECORD_PAGE",
        section: mapTabToSection(tabName),
        limit: TabFetchCoordinator.getPageSize(),
        offset: 0,
      },
      { timeoutMs: 10000 },
    );
    const commit = response?.ok
      ? TabFetchCoordinator.commitSuccess(state.tabCoordinator, tabName, requestId)
      : TabFetchCoordinator.commitError(state.tabCoordinator, tabName, requestId);
    state.tabCoordinator = commit.coordinator;
    if (!commit.accepted) {
      renderLoadMoreControls();
      return { ok: false, ignored: true };
    }
    if (!response?.ok) {
      state.tabDisplay = TabDataStore.setError(
        state.tabDisplay,
        tabName,
        response?.error || Strings.ERR_UNEXPECTED,
      );
      renderLoadMoreControls();
      if (!silent) {
        showToast(Strings.LIST_REFRESH_FAILED || Strings.ERR_UNEXPECTED, { tone: "error" });
      }
      return response;
    }
    const items = Array.isArray(response.data?.items) ? response.data.items : [];
    const pageSize = TabFetchCoordinator.getPageSize();
    state.tabDisplay = TabDataStore.setPage(state.tabDisplay, tabName, {
      items,
      hasMore: items.length >= pageSize,
      total: Number.isFinite(response.data?.total) ? response.data.total : 0,
      offset: 0,
    });
    renderLoadMoreControls();
    return response;
  }

  async function loadTabPageMore(tabName) {
    if (tabName === "inProgress") {
      return { ok: true };
    }
    const tabData = TabDataStore.getTab(state.tabDisplay, tabName);
    if (!tabData.hasMore || TabFetchCoordinator.isLoading(state.tabCoordinator, tabName)) {
      return { ok: true, skipped: true };
    }
    const nextOffset = tabData.offset + TabFetchCoordinator.getPageSize();
    const { nextCoordinator, requestId } = TabFetchCoordinator.beginFetch(state.tabCoordinator, tabName);
    state.tabCoordinator = nextCoordinator;

    const response = await sendMsg(
      {
        type: "FETCH_RECORD_PAGE",
        section: mapTabToSection(tabName),
        limit: TabFetchCoordinator.getPageSize(),
        offset: nextOffset,
      },
      { timeoutMs: 10000 },
    );
    const commit = response?.ok
      ? TabFetchCoordinator.commitSuccess(state.tabCoordinator, tabName, requestId)
      : TabFetchCoordinator.commitError(state.tabCoordinator, tabName, requestId);
    state.tabCoordinator = commit.coordinator;
    if (!commit.accepted) {
      renderLoadMoreControls();
      return { ok: false, ignored: true };
    }
    if (!response?.ok) {
      renderLoadMoreControls();
      showToast(Strings.LIST_REFRESH_FAILED || Strings.ERR_UNEXPECTED, { tone: "error" });
      return response;
    }

    const items = Array.isArray(response.data?.items) ? response.data.items : [];
    const pageSize = TabFetchCoordinator.getPageSize();
    state.tabDisplay = TabDataStore.appendPage(state.tabDisplay, tabName, {
      items,
      hasMore: items.length >= pageSize,
      total: Number.isFinite(response.data?.total) ? response.data.total : 0,
      offset: nextOffset,
    });
    renderLoadMoreControls();
    if (state.lastLocalData && state.lastSessionData) {
      renderWorkspaceFromCache(state.lastLocalData, state.lastSessionData);
    }
    return response;
  }

  function renderWorkspaceFromCache(localData, sessionData) {
    state.lastLocalData = localData;
    state.lastSessionData = sessionData;
    const activeSubmitId = sessionData.active_submit_id || null;
    const submitBatch = sessionData.submit_batch;
    const archiveBatch = sessionData.archive_batch;
    const mergedBatchState = {
      ...(submitBatch && typeof submitBatch === "object" ? submitBatch : {}),
      queue: [
        ...(Array.isArray(submitBatch?.queue) ? submitBatch.queue : []),
        ...(Array.isArray(archiveBatch?.queue) ? archiveBatch.queue : []),
      ],
      results: {
        ...((submitBatch && typeof submitBatch.results === "object" && !Array.isArray(submitBatch.results))
          ? submitBatch.results
          : {}),
        ...((archiveBatch && typeof archiveBatch.results === "object" && !Array.isArray(archiveBatch.results))
          ? archiveBatch.results
          : {}),
      },
    };
    const pending = TabDataStore.getTab(state.tabDisplay, "pending");
    const submitted = TabDataStore.getTab(state.tabDisplay, "submitted");
    const failed = TabDataStore.getTab(state.tabDisplay, "failed");
    const serverSections = buildRenderableServerSections(
      {
        pending: pending.items,
        submitted: submitted.items,
        failed: failed.items,
      },
      sessionData.last_submit_result || null,
    );
    const mergedSections = QueueFilter.mergeOptimisticSections({
      serverSections,
      batchState: mergedBatchState,
      activeSubmitId,
    });
    const sections = sortSectionsForRender({
      sections: mergedSections,
      sessionData,
    });
    const selectableIds = new Set([
      ...(sections.pending || []).map((record) => record.upload_id).filter(Boolean),
      ...(sections.failed || []).map((record) => record.upload_id).filter(Boolean),
    ]);
    state.selectedUploadIds = reconcileSelectedUploadIds(state.selectedUploadIds, selectableIds);
    const isBatchRunning = isBatchCurrentlyRunning(sessionData);
    const submitAvailability = getSubmitActionAvailability(localData);
    state.canSubmitSelection = submitAvailability.canSubmit;
    state.submitActionBlockedReason = submitAvailability.reason;

    state.sectionData = sections;
    applySummaryContext(localData);
    renderContactDefaultsNudge(localData);
    renderSubmissionBanner(sessionData);

    const pendingRecords = sections.pending.map((record) => ({
      ...record,
      _selected: state.selectedUploadIds.has(record.upload_id),
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
      _selected: state.selectedUploadIds.has(record.upload_id),
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
    setSectionVisibility(state.activeTab);
    renderLoadMoreControls();
    updateSubmitSelectionAction({
      isBatchRunning,
      canSubmit: state.canSubmitSelection,
    });
    $("submit-all-btn").onclick = () => {
      toggleSelectedActionMenu();
    };
  }

  function updateSubmitSelectionAction({ isBatchRunning, canSubmit }, doc = document) {
    const submitButton = $("submit-all-btn", doc);
    if (!submitButton) {
      return;
    }
    const actionState = buildSubmitSelectionActionState({
      selectedCount: state.selectedUploadIds.size,
      isBatchRunning,
      canSubmit,
    });
    submitButton.classList.toggle("hidden", actionState.hidden);
    submitButton.disabled = actionState.disabled;
    submitButton.textContent = actionState.label;
    const submitActionButton = $("selected-action-submit-btn", doc);
    if (submitActionButton) {
      submitActionButton.disabled = actionState.submitDisabled;
      submitActionButton.title = !canSubmit ? (state.submitActionBlockedReason || Strings.CONTRACT_ACTION_REQUIRED) : "";
    }
    const markAllButton = $("mark-all-btn", doc);
    if (markAllButton) {
      const selectableCount = (state.sectionData?.pending?.length || 0) + (state.sectionData?.failed?.length || 0);
      markAllButton.classList.toggle("hidden", selectableCount === 0);
    }
    if (actionState.disabled) {
      closeSelectedActionMenu(doc);
    }
  }

  async function getContractsForUi() {
    return ContractSelect.fetchContracts();
  }

  async function resolveContextAfterContracts(localData, contracts) {
    const activeUiContext = ContextChange.normalizeActiveUiContext(
      localData.active_ui_context || (await ContextChange.getActiveUiContext()),
    );
    const preferredContractId = localData.masar_contract_id || activeUiContext.contract_id || null;
    const resolution = ContextChange.resolveContractContext(activeUiContext, contracts, preferredContractId);

    let nextContext = resolution.nextContext;
    if (resolution.mode === "selected" && resolution.selectedContract) {
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

  function renderLoadMoreControls(doc = document) {
    for (const tabName of SERVER_TABS) {
      const button = $(`${tabName}-load-more`, doc);
      if (!button) {
        continue;
      }
      const tabData = TabDataStore.getTab(state.tabDisplay, tabName);
      const loading = TabFetchCoordinator.isLoading(state.tabCoordinator, tabName);
      button.classList.toggle("hidden", !tabData.hasMore);
      button.disabled = loading;
      button.textContent = loading ? Strings.LOADING : Strings.ACTION_LOAD_MORE;
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

  async function submitBatch(uploadIds) {
    if (!(await ensureActionContext())) {
      return;
    }
    const selectedIds = [...new Set((Array.isArray(uploadIds) ? uploadIds : []).filter(Boolean))];
    if (!selectedIds.length) {
      return;
    }
    const selectedTotal = selectedIds.length;
    const confirmed = window.confirm(Strings.SUBMIT_ALL_CONFIRM(selectedTotal));
    if (!confirmed) {
      return;
    }
    const response = await sendMsg({
      type: "SUBMIT_BATCH",
      uploadIds: selectedIds,
    }, { timeoutMs: 30000 });
    if (response?.ok === true && response?.queued === true) {
      state.selectedUploadIds = new Set();
    }
    await handleSubmitResponse({
      response,
      uploadIds: selectedIds,
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

  function getSubmitEligibleSelectionIds(uploadIds, sectionData = null) {
    const source = sectionData || {};
    const eligibleIds = new Set([
      ...(source.pending || []).map((record) => record.upload_id),
      ...(source.failed || []).map((record) => record.upload_id),
    ].filter(Boolean));
    return (Array.isArray(uploadIds) ? uploadIds : []).filter((uploadId) => eligibleIds.has(uploadId));
  }

  async function archiveSelected(uploadIds) {
    const selectedIds = [...new Set((Array.isArray(uploadIds) ? uploadIds : []).filter(Boolean))];
    if (!selectedIds.length) {
      return;
    }
    const response = await sendMsg({ type: "ARCHIVE_BATCH", uploadIds: selectedIds }, { timeoutMs: 10000 });
    if (!response?.ok) {
      const failure = Failure.classifyFailure(response);
      if (failure.type === "relink") {
        await showRelinkRequired();
        return;
      }
      if (failure.type === "masar-login") {
        showMasarLoginRequired();
        return;
      }
      showToast(Strings.ARCHIVE_FAILED, { tone: "error" });
      return;
    }
    state.selectedUploadIds = new Set();
  }

  function closeSelectedActionMenu(doc = document) {
    const menu = $("selected-action-menu", doc);
    const trigger = $("submit-all-btn", doc);
    if (!menu || !trigger || menu.classList.contains("hidden")) {
      return;
    }
    menu.classList.add("hidden");
    trigger.setAttribute("aria-expanded", "false");
  }

  function openSelectedActionMenu(doc = document) {
    const menu = $("selected-action-menu", doc);
    const trigger = $("submit-all-btn", doc);
    if (!menu || !trigger || trigger.disabled) {
      return;
    }
    menu.classList.remove("hidden");
    trigger.setAttribute("aria-expanded", "true");
  }

  function toggleSelectedActionMenu(doc = document) {
    const menu = $("selected-action-menu", doc);
    if (!menu) {
      return;
    }
    if (menu.classList.contains("hidden")) {
      openSelectedActionMenu(doc);
      return;
    }
    closeSelectedActionMenu(doc);
  }

  async function runSelectedAction(action) {
    if (action === "mark-all") {
      const allSelectableIds = new Set([
        ...(state.sectionData?.pending || []).map((r) => r.upload_id),
        ...(state.sectionData?.failed || []).map((r) => r.upload_id),
      ].filter(Boolean));
      state.selectedUploadIds = allSelectableIds;
      closeSelectedActionMenu();
      renderWorkspaceFromCache(state.lastLocalData, state.lastSessionData);
      return;
    }
    const selectedIds = [...state.selectedUploadIds];
    if (!selectedIds.length) {
      closeSelectedActionMenu();
      return;
    }
    if (action === "submit") {
      if (!state.canSubmitSelection) {
        showToast(state.submitActionBlockedReason || Strings.CONTRACT_ACTION_REQUIRED, { tone: "error" });
        closeSelectedActionMenu();
        return;
      }
      const eligibleIds = getSubmitEligibleSelectionIds(selectedIds, state.sectionData);
      if (eligibleIds.length !== selectedIds.length) {
        showToast(Strings.ACTION_SUBMIT_REQUIRES_RETRYABLE, { tone: "error" });
        return;
      }
      closeSelectedActionMenu();
      await submitBatch(selectedIds);
      return;
    }
    if (action === "archive") {
      closeSelectedActionMenu();
      await archiveSelected(selectedIds);
    }
  }

  async function loadMainWorkspace({ showLoading = true, fetchRecords = true, refreshContracts = false } = {}) {
    const loadId = ++state.workspaceLoadId;

    if (showLoading) {
      showScreen("loading");
    }
    try {
      let [localData, sessionData, pageResponse] = await Promise.all([
        localGet([
          "masar_entity_id",
          "masar_user_name",
          "masar_contract_id",
          "submit_auth_required",
          "masar_contract_name_ar",
          "masar_contract_name_en",
          "masar_contract_state",
          "active_ui_context",
          "agency_email",
          "agency_phone",
        ]),
        sessionGet([
          "submit_batch",
          "active_submit_id",
          "archive_batch",
          "active_archive_id",
          "last_submit_result",
          "last_archive_result",
        ]),
        fetchRecords ? loadTabPage(state.activeTab, { silent: true }) : Promise.resolve({ ok: true }),
      ]);

      if (loadId !== state.workspaceLoadId) return;

      const contracts = await getContractsForUi({ forceRefresh: refreshContracts });
      if (loadId !== state.workspaceLoadId) return;

      localData = await resolveContextAfterContracts(localData, contracts);
      if (loadId !== state.workspaceLoadId) return;

      if (!pageResponse?.ok && !pageResponse?.ignored) {
        const failure = Failure.classifyFailure(pageResponse);
        if (failure.type === "relink") {
          await showRelinkRequired();
          return;
        }
        const activeTabData = state.activeTab === "inProgress"
          ? null
          : TabDataStore.getTab(state.tabDisplay, state.activeTab);
        const hasUsableData = state.activeTab === "inProgress" || (activeTabData && activeTabData.items.length > 0);
        if (!hasUsableData) {
          showError(pageResponse?.error || Strings.ERR_UNEXPECTED);
          return;
        }
        showToast(Strings.LIST_REFRESH_FAILED || Strings.ERR_UNEXPECTED, { tone: "error" });
      }

      if (localData.submit_auth_required === "masar-auth") {
        showMasarLoginRequired();
        return;
      }
      if (localData.submit_auth_required === "backend-auth") {
        await showRelinkRequired();
        return;
      }

      renderWorkspaceFromCache(localData, sessionData);
      const counts = await loadServerCounts();
      if (loadId !== state.workspaceLoadId) return;

      renderMetrics(counts);
      await populateContractDropdown(localData.masar_contract_id, document, { forceRefresh: refreshContracts });
      if (loadId !== state.workspaceLoadId) return;

      showScreen("main");
      activateTab(state.activeTab);
    } catch (error) {
      if (loadId === state.workspaceLoadId) {
        const failure = Failure.classifyFailure(error);
        if (failure.type === "masar-login") {
          showMasarLoginRequired();
          return;
        }
        if (failure.type === "relink") {
          await showRelinkRequired();
          return;
        }
        showError(error?.message || Strings.ERR_UNEXPECTED);
      }
    }
  }

  function populateSettings(values) {
    $("settings-email").value = values.agency_email || "";
    $("settings-phone-cc").value = values.agency_phone_country_code || "967";
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

  function bindStorageListener() {
    if (typeof chrome === "undefined" || !chrome.storage?.session?.onChanged) return;
    // Tracks whether any in-flight debounce cycle saw a batch clear. Using a closure variable
    // rather than capturing per-event ensures it survives timer resets within the same cycle.
    let pendingBatchClear = false;
    chrome.storage.session.onChanged.addListener((changes) => {
      if (
        !changes.submit_batch
        && !changes.active_submit_id
        && !changes.archive_batch
        && !changes.active_archive_id
      ) return;
      if (state.currentScreen !== "main") return;
      // Detect batch completion directly from the change event's oldValue — more reliable than
      // comparing state.lastSessionData, which may not have seen the in-progress state when an
      // operation (e.g. a fast archive) completes within the 50ms debounce window.
      if (
        (changes.submit_batch?.newValue == null && changes.submit_batch?.oldValue != null)
        || (changes.archive_batch?.newValue == null && changes.archive_batch?.oldValue != null)
      ) {
        pendingBatchClear = true;
      }
      if (state.renderTimer) clearTimeout(state.renderTimer);
      state.renderTimer = setTimeout(() => {
        state.renderTimer = null;
        const shouldReload = pendingBatchClear;
        pendingBatchClear = false;
        sessionGet([
          "submit_batch",
          "active_submit_id",
          "archive_batch",
          "active_archive_id",
        ]).then((sessionData) => {
          if (!state.lastLocalData) return;
          const prevInProgress = Number(isBatchCurrentlyRunning(state.lastSessionData));
          const nextInProgress = Number(isBatchCurrentlyRunning(sessionData));
          renderWorkspaceFromCache(state.lastLocalData, sessionData);
          if (shouldReload || (prevInProgress > 0 && nextInProgress === 0)) {
            state.tabCoordinator = TabFetchCoordinator.markAllDirty(state.tabCoordinator);
            void loadMainWorkspace({ showLoading: false, fetchRecords: true, refreshContracts: false });
          }
        });
      }, 50);
    });
  }

  async function bootstrap() {
    setStaticCopy();
    bindEvents();
    bindStorageListener();
    await init();
  }

  async function handleSubmitResponse({
    response,
    uploadIds,
    classifyFailure,
    onRelinkRequired,
    onMasarLoginRequired,
    onReload,
  }) {
    if (response?.ok && response?.queued) {
      if (Array.isArray(uploadIds) && state.lastLocalData) {
        const currentBatch = state.lastSessionData?.submit_batch;
        const currentQueue = Array.isArray(currentBatch?.queue) ? currentBatch.queue : [];
        const mergedQueue = [...new Set([...currentQueue, ...uploadIds])];
        const currentResults = currentBatch && typeof currentBatch.results === "object" && !Array.isArray(currentBatch.results)
          ? currentBatch.results
          : {};
        const nextActiveId = currentBatch?.active_id
          || mergedQueue.find((uploadId) => !Object.prototype.hasOwnProperty.call(currentResults, String(uploadId)))
          || null;
        const optimisticSession = {
          ...state.lastSessionData,
          submit_batch: {
            queue: mergedQueue,
            active_id: nextActiveId,
            results: currentResults,
            blocked_reason: currentBatch?.blocked_reason || null,
            started_at: currentBatch?.started_at || new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          active_submit_id: nextActiveId,
        };
        renderWorkspaceFromCache(state.lastLocalData, optimisticSession);
      }
      return;
    }
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

  async function ensureActionContext() {
    const localData = await localGet(["active_ui_context", "masar_contract_id"]);
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
        await localSet({ api_token: issued.sessionToken, session_expired: false, submit_auth_required: null });
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
    $("contact-defaults-nudge-btn")?.addEventListener("click", async () => {
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
      await localRemove(["api_token"]);
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
    $("pending-load-more")?.addEventListener("click", () => {
      void loadTabPageMore("pending");
    });
    $("submitted-load-more")?.addEventListener("click", () => {
      void loadTabPageMore("submitted");
    });
    $("failed-load-more")?.addEventListener("click", () => {
      void loadTabPageMore("failed");
    });
    $("mark-all-btn")?.addEventListener("click", () => {
      void runSelectedAction("mark-all");
    });
    $("selected-action-submit-btn")?.addEventListener("click", () => {
      void runSelectedAction("submit");
    });
    $("selected-action-archive-btn")?.addEventListener("click", () => {
      void runSelectedAction("archive");
    });
    $("contract-select").addEventListener("change", async (event) => {
      if (!event.target.value) {
        return;
      }
      const contracts = Array.isArray(state.contractsCache) ? state.contractsCache : await ContractSelect.fetchContracts();
      const selectedContract = contracts.find(
        (contract) => String(contract.contractId) === String(event.target.value),
      );
      const activeUiContext = await ContextChange.getActiveUiContext();
      await ContextChange.setActiveUiContext(
        ContextChange.buildExplicitContractSelectionContext(activeUiContext, selectedContract, []),
      );
      await handleContractSelectionChange({
        value: event.target.value,
        writeSelection: localSet,
        reloadWorkspace: () => loadMainWorkspace({ showLoading: false, fetchRecords: true }),
      });
    });
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        closeSelectedActionMenu();
        activateTab(tab.dataset.tab);
      });
    });
    document.addEventListener("click", (event) => {
      const wrap = $("selected-action-wrap");
      if (!wrap) {
        return;
      }
      if (wrap.contains(event.target)) {
        return;
      }
      closeSelectedActionMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeSelectedActionMenu();
      }
    });
  }

  return {
    PRE_RELEASE_SHOW_RAW_FAILURES,
    bootstrap,
    buildSubmitSelectionActionState,
    buildDisplayName,
    buildBatchBannerState,
    buildRenderableServerSections,
    getSectionEmptyNote,
    ensureActionContextState,
    getRecordNote,
    getScreenTheme,
    handleCardClick,
    handleContractSelectionChange,
    decideBootstrapAction,
    getSubmissionContextMismatchToast,
    handleResumeBatchResponse,
    handleSubmitResponse,
    loadTabPageMore,
    isBatchCurrentlyRunning,
    renderPendingCard,
    renderLoadMoreControls,
    reconcileSelectedUploadIds,
    sortSectionsForRender,
    buildContractPickerState,
    setDetailLinkLoadingState,
    getSubmissionContextMismatch,
    showToast,
  };
});
