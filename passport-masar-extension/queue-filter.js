(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarQueueFilter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function normalizeBatchState(batchState, activeSubmitId = null) {
    const batchIds = Array.isArray(batchState)
      ? batchState
      : Array.isArray(batchState?.queued_ids)
        ? batchState.queued_ids
        : [];
    const activeId = Array.isArray(batchState) ? activeSubmitId : batchState?.active_id || activeSubmitId || null;
    const submittedIds = new Set(
      Array.isArray(batchState?.submitted_ids) ? batchState.submitted_ids : [],
    );
    const failedIds = new Set(
      Array.isArray(batchState?.failed_ids) ? batchState.failed_ids : [],
    );
    const inProgressIds = new Set(batchIds);
    if (activeId) {
      inProgressIds.add(activeId);
    }
    return {
      inProgressIds,
      activeId,
      submittedIds,
      failedIds,
    };
  }

  function filterServerSections(caches = {}) {
    return {
      pending: Array.isArray(caches.pending) ? caches.pending.slice() : [],
      submitted: Array.isArray(caches.submitted) ? caches.submitted.slice() : [],
      failed: Array.isArray(caches.failed) ? caches.failed.slice() : [],
    };
  }

  function mergeOptimisticSections({ serverSections, batchState, activeSubmitId = null }) {
    const normalized = normalizeBatchState(batchState, activeSubmitId);
    const sections = {
      pending: [],
      inProgress: [],
      submitted: [],
      failed: [],
    };
    const appendedSubmitted = new Set();
    const appendedFailed = new Set();

    const processedIds = new Set();
    const placeRecord = (record, sourceSection) => {
      if (processedIds.has(record.upload_id)) {
        return;
      }
      processedIds.add(record.upload_id);
      if (normalized.inProgressIds.has(record.upload_id)) {
        sections.inProgress.push(record);
        return;
      }
      if (normalized.submittedIds.has(record.upload_id)) {
        if (!appendedSubmitted.has(record.upload_id)) {
          sections.submitted.push({ ...record, masar_status: "submitted" });
          appendedSubmitted.add(record.upload_id);
        }
        return;
      }
      if (normalized.failedIds.has(record.upload_id)) {
        if (!appendedFailed.has(record.upload_id)) {
          sections.failed.push({ ...record, masar_status: "failed" });
          appendedFailed.add(record.upload_id);
        }
        return;
      }
      if (sourceSection === "submitted" || record.masar_status === "submitted") {
        sections.submitted.push(record);
        return;
      }
      if (
        sourceSection === "failed"
        || record.upload_status === "failed"
        || record.masar_status === "failed"
        || record.masar_status === "missing"
      ) {
        sections.failed.push(record);
        return;
      }
      sections.pending.push(record);
    };

    // Precedence: submitted server cache > failed server cache > pending server cache.
    // This prevents stale pending data from hiding fresher status in other tabs.
    const submittedItems = Array.isArray(serverSections?.submitted) ? serverSections.submitted : [];
    const failedItems = Array.isArray(serverSections?.failed) ? serverSections.failed : [];
    const pendingItems = Array.isArray(serverSections?.pending) ? serverSections.pending : [];

    for (const record of submittedItems) {
      placeRecord(record, "submitted");
    }
    for (const record of failedItems) {
      placeRecord(record, "failed");
    }
    for (const record of pendingItems) {
      placeRecord(record, "pending");
    }

    return sections;
  }

  return {
    filterServerSections,
    mergeOptimisticSections,
    normalizeBatchState,
  };
});
