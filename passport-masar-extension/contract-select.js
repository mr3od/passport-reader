(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarContractSelect = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function sendMessage(message) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(message, (response) => {
        resolve(response);
      });
    });
  }

  async function fetchContracts() {
    const response = await sendMessage({ type: "FETCH_CONTRACTS" });
    if (!response || !response.ok) {
      throw new Error(response?.error || "contracts-unavailable");
    }
    return Array.isArray(response.contracts) ? response.contracts : [];
  }

  function resolveContractSelection(contracts, currentContractId = null) {
    const activeContracts = (Array.isArray(contracts) ? contracts : []).filter(
      (contract) => contract?.contractStatus?.id === 0,
    );
    if (activeContracts.length === 0) {
      return { selectedContract: null, showDropdown: false };
    }
    if (activeContracts.length === 1) {
      return { selectedContract: activeContracts[0], showDropdown: false };
    }
    if (currentContractId) {
      const selectedContract = activeContracts.find(
        (contract) => String(contract.contractId) === String(currentContractId),
      );
      if (selectedContract) {
        return { selectedContract, showDropdown: true };
      }
    }
    return { selectedContract: null, showDropdown: true };
  }

  return {
    fetchContracts,
    resolveContractSelection,
  };
});
