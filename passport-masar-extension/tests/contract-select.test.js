const test = require("node:test");
const assert = require("node:assert/strict");

const { resolveContractSelection } = require("../contract-select.js");

test("resolveContractSelection keeps dropdown visible even with one active contract", () => {
  const contracts = [
    { contractId: 7, contractStatus: { id: 0 } },
    { contractId: 9, contractStatus: { id: 1 } },
  ];

  assert.deepEqual(resolveContractSelection(contracts), {
    selectedContract: null,
    showDropdown: true,
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

test("resolveContractSelection keeps an explicitly selected active contract", () => {
  const contracts = [
    { contractId: 7, contractStatus: { id: 0 } },
    { contractId: 8, contractStatus: { id: 0 } },
  ];

  assert.deepEqual(resolveContractSelection(contracts, "8"), {
    selectedContract: { contractId: 8, contractStatus: { id: 0 } },
    showDropdown: true,
  });
});
