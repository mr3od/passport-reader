(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarAuth = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function normalizeBaseUrl(apiBaseUrl) {
    return String(apiBaseUrl || "").replace(/\/+$/, "");
  }

  async function readErrorDetail(response) {
    try {
      const payload = await response.json();
      if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
        return payload.detail.trim();
      }
    } catch {
      // Ignore non-JSON error payloads.
    }
    return `HTTP ${response.status}`;
  }

  async function exchangeTempToken({ apiBaseUrl, tempToken, fetchImpl }) {
    if (!tempToken) {
      throw new Error("missing token");
    }

    const response = await fetchImpl(`${normalizeBaseUrl(apiBaseUrl)}/auth/exchange`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token: tempToken }),
    });

    if (!response.ok) {
      throw new Error(await readErrorDetail(response));
    }

    const payload = await response.json();
    if (!payload || typeof payload.session_token !== "string" || !payload.session_token) {
      throw new Error("missing session_token");
    }

    return {
      sessionToken: payload.session_token,
    };
  }

  return {
    exchangeTempToken,
    normalizeBaseUrl,
  };
});
