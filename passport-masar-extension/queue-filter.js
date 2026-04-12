(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarQueueFilter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function normalizeBatchState(batchState, activeSubmitId = null) {
    const queue = Array.isArray(batchState?.queue)
      ? batchState.queue
        .map((uploadId) => Number(uploadId))
        .filter((uploadId) => Number.isFinite(uploadId) && uploadId > 0)
      : [];
    const candidateActiveId = batchState?.active_id ?? activeSubmitId ?? null;
    const parsedActiveId = Number(candidateActiveId);
    const activeId = Number.isFinite(parsedActiveId) && parsedActiveId > 0 ? parsedActiveId : null;
    const results = batchState && typeof batchState.results === "object" && !Array.isArray(batchState.results)
      ? batchState.results
      : {};

    const submittedIds = new Set();
    const failedIds = new Set();
    const archivedIds = new Set();
    const processedIds = new Set();

    for (const [key, status] of Object.entries(results)) {
      const uploadId = Number(key);
      if (!Number.isFinite(uploadId)) {
        continue;
      }
      if (status === "submitted") {
        submittedIds.add(uploadId);
        processedIds.add(uploadId);
        continue;
      }
      if (status === "failed" || status === "missing") {
        failedIds.add(uploadId);
        processedIds.add(uploadId);
        continue;
      }
      if (status === "archived") {
        archivedIds.add(uploadId);
        processedIds.add(uploadId);
      }
    }

    const inProgressIds = new Set();
    for (const uploadId of queue) {
      if (!processedIds.has(uploadId)) {
        inProgressIds.add(uploadId);
      }
    }
    if (activeId && !processedIds.has(activeId)) {
      inProgressIds.add(activeId);
    }
    return {
      inProgressIds,
      activeId,
      submittedIds,
      failedIds,
      archivedIds,
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
      if (normalized.archivedIds.has(record.upload_id)) {
        return;
      }
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

    // Precedence: submitted > failed > pending.
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
