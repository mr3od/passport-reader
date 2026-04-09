(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarPopupFailure = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function classifyFailure(response) {
    if (!response || response.ok) {
      return { type: "none" };
    }
    if (response.failureKind === "backend-auth") {
      return { type: "relink" };
    }
    if (response.failureKind === "masar-auth") {
      return { type: "masar-login" };
    }
    if (response.status === 401) {
      return { type: "relink" };
    }
    return { type: "generic" };
  }

  return {
    classifyFailure,
  };
});
