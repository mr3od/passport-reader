const test = require("node:test");
const assert = require("node:assert/strict");

const {
  activeUiContextsEqual,
  classifyObservedContextChange,
  buildObservedEntityChangeContext,
  buildExplicitContractSelectionContext,
  resolveContractContext,
  isContractSelectable,
  isGroupSelectable,
} = require("../context-change.js");

test("classifyObservedContextChange prefers entity drift over contract drift", () => {
  const change = classifyObservedContextChange(
    {
      entity_id: "823397",
      contract_id: "224925",
    },
    {
      entity_id: "820456",
      contract_id: "223664",
    },
  );

  assert.equal(change, "entity_changed_observed");
});

test("classifyObservedContextChange ignores observed contract drift within the same entity", () => {
  const change = classifyObservedContextChange(
    {
      entity_id: "823397",
      contract_id: "224925",
    },
    {
      entity_id: "823397",
      contract_id: "223664",
    },
  );

  assert.equal(change, null);
});

test("buildObservedEntityChangeContext clears stale selections and keeps only active contracts", () => {
  const next = buildObservedEntityChangeContext(
    {
      entity_id: "823397",
      contract_id: "224925",
      group_id: "group-1",
      requires_contract_confirmation: false,
      requires_group_confirmation: false,
      available_contracts: [],
    },
    {
      entity_id: "820456",
      entity_type_id: "58",
      auth_token: "Bearer new-token",
      user_name: "Agency B",
    },
    [
      { contractId: 223664, contractStatus: { id: 0 }, companyNameAr: "نشط" },
      { contractId: 223665, contractStatus: { id: 1 }, companyNameAr: "منتهي" },
    ],
  );

  assert.equal(next.entity_id, "820456");
  assert.equal(next.entity_type_id, "58");
  assert.equal(next.contract_id, null);
  assert.equal(next.group_id, null);
  assert.equal(next.requires_contract_confirmation, true);
  assert.equal(next.requires_group_confirmation, false);
  assert.equal(next.drift_reason, "entity_changed_observed");
  assert.deepEqual(next.available_contracts.map((contract) => String(contract.contractId)), ["223664"]);
});

test("buildExplicitContractSelectionContext clears group and only keeps valid groups", () => {
  const next = buildExplicitContractSelectionContext(
    {
      entity_id: "820456",
      group_id: "old-group",
      available_groups: [],
    },
    {
      contractId: 223664,
      companyNameAr: "العقد الحالي",
      contractStatus: { id: 0, name: "Active" },
      contractEndDate: "2099-01-01T00:00:00",
    },
    [
      { id: "group-1", groupName: "جاهزة", isDeleted: false, isArchived: false, state: { id: 0 } },
      { id: "group-2", groupName: "مكتملة", isDeleted: false, isArchived: false, state: { id: 107 } },
    ],
  );

  assert.equal(next.contract_id, "223664");
  assert.equal(next.contract_name, "العقد الحالي");
  assert.equal(next.contract_state, "active");
  assert.equal(next.group_id, null);
  assert.equal(next.requires_contract_confirmation, false);
  assert.equal(next.requires_group_confirmation, true);
  assert.deepEqual(next.available_groups.map((group) => group.id), ["group-1"]);
});

test("resolveContractContext auto-selects the only selectable contract and clears confirmation", () => {
  const resolved = resolveContractContext(
    {
      entity_id: "820456",
      entity_type_id: "58",
      auth_token: "Bearer new-token",
      user_name: "Agency B",
      requires_contract_confirmation: true,
      available_contracts: [],
    },
    [
      {
        contractId: 223664,
        companyNameAr: "العقد الوحيد",
        contractStatus: { id: 0, name: "Active" },
        contractEndDate: "2099-01-01T00:00:00",
      },
    ],
    null,
  );

  assert.equal(resolved.mode, "selected");
  assert.equal(resolved.selectedContract.contractId, 223664);
  assert.equal(resolved.nextContext.contract_id, "223664");
  assert.equal(resolved.nextContext.requires_contract_confirmation, false);
  assert.equal(resolved.nextContext.drift_reason, null);
});

test("resolveContractContext keeps confirmation when multiple contracts are selectable", () => {
  const resolved = resolveContractContext(
    {
      entity_id: "820456",
      entity_type_id: "58",
      auth_token: "Bearer new-token",
      user_name: "Agency B",
      requires_contract_confirmation: true,
      available_contracts: [],
    },
    [
      {
        contractId: 223664,
        companyNameAr: "العقد الأول",
        contractStatus: { id: 0, name: "Active" },
        contractEndDate: "2099-01-01T00:00:00",
      },
      {
        contractId: 223665,
        companyNameAr: "العقد الثاني",
        contractStatus: { id: 0, name: "Active" },
        contractEndDate: "2099-01-01T00:00:00",
      },
    ],
    null,
  );

  assert.equal(resolved.mode, "needs-contract-choice");
  assert.equal(resolved.selectedContract, null);
  assert.equal(resolved.nextContext.contract_id, null);
  assert.equal(resolved.nextContext.requires_contract_confirmation, true);
  assert.deepEqual(resolved.nextContext.available_contracts.map((contract) => String(contract.contractId)), ["223664", "223665"]);
});

test("resolveContractContext clears contract selection when there are no selectable contracts", () => {
  const resolved = resolveContractContext(
    {
      entity_id: "820456",
      entity_type_id: "58",
      auth_token: "Bearer new-token",
      user_name: "Agency B",
      contract_id: "223664",
      contract_name: "عقد قديم",
      requires_contract_confirmation: true,
      available_contracts: [],
    },
    [
      {
        contractId: 223664,
        companyNameAr: "عقد منتهي",
        contractStatus: { id: 0, name: "Active" },
        contractEndDate: "2020-01-01T00:00:00",
      },
    ],
    "223664",
  );

  assert.equal(resolved.mode, "no-selectable-contracts");
  assert.equal(resolved.selectedContract, null);
  assert.equal(resolved.nextContext.contract_id, null);
  assert.equal(resolved.nextContext.requires_contract_confirmation, false);
  assert.equal(resolved.nextContext.available_contracts.length, 0);
});

test("activeUiContextsEqual treats identical normalized contexts as unchanged", () => {
  assert.equal(
    activeUiContextsEqual(
      {
        entity_id: "820456",
        contract_id: "223664",
        contract_state: "active",
        available_contracts: [{ contractId: 223664 }],
      },
      {
        entity_id: "820456",
        contract_id: "223664",
        contract_state: "active",
        available_contracts: [{ contractId: 223664 }],
        available_groups: [],
      },
    ),
    true,
  );
});

test("isContractSelectable only accepts active contracts", () => {
  assert.equal(isContractSelectable({ contractStatus: { id: 0 } }), true);
  assert.equal(isContractSelectable({ contractStatus: { id: 1 } }), false);
  assert.equal(isContractSelectable(null), false);
});

test("isContractSelectable rejects expired contracts even when status is active", () => {
  assert.equal(
    isContractSelectable({
      contractStatus: { id: 0 },
      contractEndDate: "2020-01-01T00:00:00",
    }),
    false,
  );
});

test("isGroupSelectable blocks deleted, archived, completed, and returned groups", () => {
  assert.equal(isGroupSelectable({ isDeleted: false, isArchived: false, state: { id: 0 } }), true);
  assert.equal(isGroupSelectable({ isDeleted: true, isArchived: false, state: { id: 0 } }), false);
  assert.equal(isGroupSelectable({ isDeleted: false, isArchived: true, state: { id: 0 } }), false);
  assert.equal(isGroupSelectable({ isDeleted: false, isArchived: false, state: { id: 107 } }), false);
  assert.equal(isGroupSelectable({ isDeleted: false, isArchived: false, state: { id: 9 } }), false);
});
