(function (root, factory) {
  const api = factory(root.MasarStrings || require("./strings.js"));
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarStatus = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (strings) {
  function getStatusLabel({ upload_status, masar_status, review_status, inProgress }) {
    if (upload_status === "failed" || masar_status === "failed") {
      return strings.STATUS_FAILED;
    }
    if (masar_status === "missing") {
      return strings.STATUS_MISSING;
    }
    if (masar_status === "submitted" && review_status === "needs_review") {
      return strings.STATUS_SUBMITTED_NEEDS_REVIEW;
    }
    if (masar_status === "submitted") {
      return strings.STATUS_SUBMITTED;
    }
    if (inProgress === "active") {
      return strings.STATUS_IN_PROGRESS;
    }
    if (inProgress === "queued" || inProgress === true) {
      return strings.STATUS_QUEUED_IN_BATCH;
    }
    if (review_status === "needs_review") {
      return strings.STATUS_NEEDS_REVIEW;
    }
    return strings.STATUS_READY;
  }

  function getStatusColor({ upload_status, masar_status, review_status, inProgress }) {
    if (upload_status === "failed" || masar_status === "failed") {
      return "#C53B22";
    }
    if (masar_status === "missing") {
      return "#B87912";
    }
    if (masar_status === "submitted" && review_status === "needs_review") {
      return "#B87912";
    }
    if (masar_status === "submitted") {
      return "#247A53";
    }
    if (inProgress) {
      return "#5D6879";
    }
    if (review_status === "needs_review") {
      return "#B87912";
    }
    return "#285AA6";
  }

  return {
    getStatusColor,
    getStatusLabel,
  };
});
