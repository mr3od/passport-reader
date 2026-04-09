const test = require("node:test");
const assert = require("node:assert/strict");

const {
  fetchContracts,
  getSelectableContracts,
  resolveContractSelection,
} = require("../contract-select.js");

test("getSelectableContracts excludes expired contracts even when status is active", () => {
  const contracts = getSelectableContracts([
    {
      contractId: 1,
      contractStatus: { id: 0 },
      contractEndDate: "2020-01-01T00:00:00",
    },
    {
      contractId: 2,
      contractStatus: { id: 0 },
      contractEndDate: "2099-01-01T00:00:00",
    },
  ]);

  assert.deepEqual(contracts.map((contract) => contract.contractId), [2]);
});

test("resolveContractSelection auto-selects a single selectable contract and hides the dropdown", () => {
  const resolution = resolveContractSelection([
    {
      contractId: 7,
      companyNameAr: "العقد الوحيد",
      contractStatus: { id: 0 },
      contractEndDate: "2099-01-01T00:00:00",
    },
  ]);

  assert.equal(resolution.selectedContract.contractId, 7);
  assert.equal(resolution.showDropdown, false);
  assert.equal(resolution.autoSelected, true);
});

test("fetchContracts preserves masar auth failure metadata for popup routing", async () => {
  global.chrome = {
    runtime: {
      lastError: null,
      sendMessage(_message, callback) {
        callback({ ok: false, error: "contracts 401", failureKind: "masar-auth", status: 401 });
      },
    },
  };

  await assert.rejects(
    fetchContracts(),
    (error) => {
      assert.equal(error.message, "contracts 401");
      assert.equal(error.failureKind, "masar-auth");
      assert.equal(error.status, 401);
      return true;
    },
  );

  delete global.chrome;
});
