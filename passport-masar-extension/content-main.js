// Runs in MAIN world — same JS context as the Angular app.
// Intercepts the page's own XHR/fetch calls and posts captured data to window.
(function () {
  function shouldCapture(url) {
    if (url.includes("GetGroupList"))    return "GROUP_LIST_CAPTURED";
    if (url.includes("GetContractList")) return "CONTRACT_LIST_CAPTURED";
    return null;
  }

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__url = url;
    return origOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function (body) {
    this.addEventListener("load", function () {
      const type = this.__url && this.status === 200 && shouldCapture(this.__url);
      if (type) {
        try {
          const data = JSON.parse(this.responseText);
          window.postMessage({ __masarExt: type, data }, "*");
        } catch (_) {}
      }
    });
    return origSend.call(this, body);
  };

  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const url = args[0] instanceof Request ? args[0].url : String(args[0]);
    const response = await origFetch.apply(this, args);
    const type = shouldCapture(url);
    if (type && response.ok) {
      response.clone().json().then((data) => {
        window.postMessage({ __masarExt: type, data }, "*");
      }).catch(() => {});
    }
    return response;
  };
})();
