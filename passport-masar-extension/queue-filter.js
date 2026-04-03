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
    const inProgressIds = new Set(batchIds);
    if (activeId) {
      inProgressIds.add(activeId);
    }
    return {
      inProgressIds,
      activeId,
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
      submitted: Array.isArray(serverSections?.submitted) ? serverSections.submitted.slice() : [],
      failed: Array.isArray(serverSections?.failed) ? serverSections.failed.slice() : [],
    };

    for (const record of Array.isArray(serverSections?.pending) ? serverSections.pending : []) {
      if (normalized.inProgressIds.has(record.upload_id)) {
        sections.inProgress.push(record);
        continue;
      }
      sections.pending.push(record);
    }

    for (const record of sections.failed.slice()) {
      if (normalized.inProgressIds.has(record.upload_id)) {
        sections.failed = sections.failed.filter((item) => item.upload_id !== record.upload_id);
        sections.inProgress.push(record);
      }
    }

    return sections;
  }

  return {
    filterServerSections,
    mergeOptimisticSections,
    normalizeBatchState,
  };
});
