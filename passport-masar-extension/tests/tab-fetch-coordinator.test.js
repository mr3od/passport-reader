const test = require("node:test");
const assert = require("node:assert/strict");

const TabFetchCoordinator = require("../tab-fetch-coordinator.js");

test("TabFetchCoordinator.create seeds independent per-tab request state", () => {
  const coordinator = TabFetchCoordinator.create();

  assert.deepEqual(coordinator.pending, {
    status: "idle",
    dirty: true,
    requestId: 0,
  });
  assert.deepEqual(coordinator.submitted, {
    status: "idle",
    dirty: true,
    requestId: 0,
  });
  assert.deepEqual(coordinator.failed, {
    status: "idle",
    dirty: true,
    requestId: 0,
  });
});

test("TabFetchCoordinator.beginFetch advances only the targeted tab", () => {
  const coordinator = TabFetchCoordinator.create();
  const { nextCoordinator, requestId } = TabFetchCoordinator.beginFetch(coordinator, "pending");

  assert.equal(requestId, 1);
  assert.deepEqual(nextCoordinator.pending, {
    status: "loading",
    dirty: true,
    requestId: 1,
  });
  assert.equal(nextCoordinator.submitted, coordinator.submitted);
});

test("TabFetchCoordinator.commitSuccess accepts only the newest request per tab", () => {
  const coordinator = TabFetchCoordinator.create();
  const first = TabFetchCoordinator.beginFetch(coordinator, "pending");
  const second = TabFetchCoordinator.beginFetch(first.nextCoordinator, "pending");

  const stale = TabFetchCoordinator.commitSuccess(second.nextCoordinator, "pending", first.requestId);
  const fresh = TabFetchCoordinator.commitSuccess(second.nextCoordinator, "pending", second.requestId);

  assert.equal(stale.accepted, false);
  assert.equal(stale.coordinator, second.nextCoordinator);
  assert.equal(fresh.accepted, true);
  assert.deepEqual(fresh.coordinator.pending, {
    status: "ready",
    dirty: false,
    requestId: 2,
  });
});

test("TabFetchCoordinator.commitError is scoped per tab request id", () => {
  const coordinator = TabFetchCoordinator.create();
  const pendingFetch = TabFetchCoordinator.beginFetch(coordinator, "pending");
  const failedFetch = TabFetchCoordinator.beginFetch(pendingFetch.nextCoordinator, "failed");

  const result = TabFetchCoordinator.commitError(failedFetch.nextCoordinator, "failed", failedFetch.requestId);

  assert.equal(result.accepted, true);
  assert.deepEqual(result.coordinator.failed, {
    status: "error",
    dirty: true,
    requestId: 1,
  });
  assert.deepEqual(result.coordinator.pending, {
    status: "loading",
    dirty: true,
    requestId: 1,
  });
});

test("TabFetchCoordinator dirty helpers and page size stay deterministic", () => {
  const markedOne = TabFetchCoordinator.markDirty(TabFetchCoordinator.create(), "submitted");
  const markedAll = TabFetchCoordinator.markAllDirty(
    TabFetchCoordinator.commitSuccess(
      TabFetchCoordinator.beginFetch(TabFetchCoordinator.create(), "pending").nextCoordinator,
      "pending",
      1,
    ).coordinator,
  );

  assert.equal(TabFetchCoordinator.isDirty(markedOne, "submitted"), true);
  assert.equal(TabFetchCoordinator.isLoading(markedOne, "submitted"), false);
  assert.equal(TabFetchCoordinator.isDirty(markedAll, "pending"), true);
  assert.equal(TabFetchCoordinator.getPageSize(), 50);
});
