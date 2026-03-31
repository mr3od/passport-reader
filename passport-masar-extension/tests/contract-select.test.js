const test = require("node:test");
const assert = require("node:assert/strict");

const { resolveContractSelection } = require("../contract-select.js");

test("resolveContractSelection auto-selects the only active contract", () => {
  const contracts = [
    { contractId: 7, contractStatus: { id: 0 } },
    { contractId: 9, contractStatus: { id: 1 } },
  ];

  assert.deepEqual(resolveContractSelection(contracts), {
    selectedContract: { contractId: 7, contractStatus: { id: 0 } },
    showDropdown: false,
  });
});

test("resolveContractSelection requests a dropdown when multiple active contracts exist", () => {
  const contracts = [
    { contractId: 7, contractStatus: { id: 0 } },
    { contractId: 8, contractStatus: { id: 0 } },
  ];

  assert.deepEqual(resolveContractSelection(contracts), {
    selectedContract: null,
    showDropdown: true,
  });
});
