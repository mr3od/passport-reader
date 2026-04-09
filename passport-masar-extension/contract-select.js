(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarContractSelect = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const ContextChange =
    globalThis.MasarContextChange || (typeof require === "function" ? require("./context-change.js") : undefined);

  function sendMessage(message) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(response);
      });
    });
  }

  async function fetchContracts() {
    const response = await sendMessage({ type: "FETCH_CONTRACTS" });
    if (!response || !response.ok) {
      const error = new Error(response?.error || "contracts-unavailable");
      if (response && typeof response === "object") {
        Object.assign(error, response);
      }
      throw error;
    }
    return Array.isArray(response.contracts) ? response.contracts : [];
  }

  function isSelectableContract(contract) {
    return ContextChange.isContractSelectable(contract);
  }

  function getSelectableContracts(contracts) {
    return ContextChange.filterSelectableContracts(contracts);
  }

  function resolveContractSelection(contracts, currentContractId = null) {
    const selectableContracts = getSelectableContracts(contracts);
    if (selectableContracts.length === 0) {
      return { selectedContract: null, showDropdown: false, autoSelected: false };
    }
    if (currentContractId) {
      const selectedContract = selectableContracts.find(
        (contract) => String(contract.contractId) === String(currentContractId),
      );
      if (selectedContract) {
        return {
          selectedContract,
          showDropdown: selectableContracts.length > 1,
          autoSelected: false,
        };
      }
    }
    if (selectableContracts.length === 1) {
      return {
        selectedContract: selectableContracts[0],
        showDropdown: false,
        autoSelected: true,
      };
    }
    return { selectedContract: null, showDropdown: true, autoSelected: false };
  }

  return {
    fetchContracts,
    getSelectableContracts,
    isSelectableContract,
    resolveContractSelection,
  };
});
