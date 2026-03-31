(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarQueueFilter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function filterQueueSections(records, inProgressIds = new Set()) {
    const sections = {
      pending: [],
      inProgress: [],
      submitted: [],
      failed: [],
    };

    for (const record of Array.isArray(records) ? records : []) {
      if (record.upload_status === "failed" || record.masar_status === "failed") {
        sections.failed.push(record);
        continue;
      }
      if (record.masar_status === "submitted") {
        sections.submitted.push(record);
        continue;
      }
      if (record.upload_status === "processed" && !record.masar_status) {
        if (inProgressIds.has(record.upload_id)) {
          sections.inProgress.push(record);
        } else {
          sections.pending.push(record);
        }
      }
    }

    return sections;
  }

  return {
    filterQueueSections,
  };
});
