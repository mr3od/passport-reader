Got it. With this full architecture context, I’d recommend a **much simpler state/data model** than the current popup, but also one that respects your real production constraints:

- plain MV3 extension
- popup talks to background via messages
- background owns long-running orchestration
- popup is storage-reactive today
- group is intentionally hidden
- explicit contract selection matters
- optimistic in-progress state comes from `chrome.storage.session`
- no need to overbuild

So the goal should be:

> **Keep background as the source of truth for workflow state, and make the popup a thin query-driven view.**

That means **stop inventing a custom popup cache/state machine**.

---

# Final recommendation

## Use this stack

### 1. **Preact**
For the popup UI.

Why:
- tiny
- fast
- simple
- ideal for extension popup size
- much lighter than React while giving component rendering and declarative UI

### 2. **TanStack Query**
For async state and caching.

Why:
- removes almost all custom cache logic
- handles loading/error/stale/refetch
- handles query invalidation cleanly
- much simpler than your current `tabCache + countsState + lastSessionData + lastLocalData` model

### 3. **Zustand**
Only for tiny UI-only local state.

Why:
- great for:
  - active tab
  - current screen override
  - toast
  - skipped IDs
  - maybe selected dialog state
- not for server/cache state

### 4. **Zod** (optional but recommended)
For validating message/storage payloads.

Why:
- your popup depends on many storage/message payloads
- one malformed response can break rendering
- lightweight safety net

---

# The key architecture change

## Today
The popup has become a mini state engine:
- local storage snapshots
- session snapshots
- tab caches
- contract cache
- count cache
- optimistic overlay state
- special-case submit patch state
- DOM rendering logic

This is where the bugs come from.

## Better model
Make the popup just a view over a few **queries**:

- bootstrap/session readiness
- workspace context
- contracts
- counts
- records by tab
- submission state

And a few **local UI atoms**:

- active tab
- toast
- skipped IDs
- maybe “settings open”

That’s it.

---

# Important constraint from your production architecture

Because your background worker already owns:
- submission orchestration
- context sync
- record fetching
- session state
- badge logic
- notifications

you do **not** need a heavy client-side state model in the popup.

That means:

## Do not build:
- Redux
- normalized entity graph
- custom optimistic state engine
- homegrown cache invalidation system
- custom stale-time scheduler

That would repeat the same mistake in a different form.

---

# KISS / YAGNI target design

## Ownership

### Background owns
- all real business state
- all submit orchestration
- all session sync
- all authoritative submission state
- all backend/Masar integration

### Popup query layer owns
- cached reads of background/storage-backed state
- simple refresh/invalidation

### Popup UI store owns only
- selected tab
- hidden/skipped IDs
- toast
- local modals/dialog flags

---

# What the popup should query

You do not need many query types.

## 1. `bootstrap`
Used to decide:
- setup
- activate
- session-expired
- main
- error

This can replace a lot of imperative `init()` logic.

### Data returned
Something like:
```ts
type BootstrapData = {
  screen: "setup" | "activate" | "session-expired" | "main";
  auth: {
    hasApiToken: boolean;
    submitAuthRequired: string | null;
  };
  context: {
    entityId: string | null;
    contractId: string | null;
    contractState: string | null;
    activeUiContext: unknown;
  };
};
```

---

## 2. `workspaceContext`
Used for:
- entity summary
- contract summary
- contract state pill
- contact-defaults nudge
- contract picker state

This can come from local storage + resolved contracts.

---

## 3. `contracts`
Used for contract dropdown.

No manual TTL cache needed unless profiling proves it matters.

TanStack Query already supports `staleTime`.

---

## 4. `counts`
Used for summary counts and tab badges.

---

## 5. `records(section)`
Used for:
- pending
- submitted
- failed

For pagination, use `useInfiniteQuery`.

For in-progress, don’t fake a server cache. Use submission state.

---

## 6. `submissionState`
Used for:
- in-progress tab
- progress banner
- batch resume action
- immediate “queued/in-progress” display

This should read from `chrome.storage.session`, because that’s already your intended transient source of truth.

---

# What should *not* be cached manually anymore

Remove custom popup cache for:

- tab pages
- counts
- contracts TTL
- latest local snapshot
- latest session snapshot
- workspace loading queue flags

These should become:
- query results
- query status
- query invalidation

---

# Very important simplification: stop patching records in the popup

Right now the popup tries to do too much:

- merge server sections
- merge optimistic batch state
- patch last submit result
- hide skipped items
- recalculate counts

This is the heart of the bug source.

## Simpler rule
The popup should do only these view transformations:

1. read current records for the active tab
2. read submission state
3. hide locally skipped pending items
4. render

That’s all.

If records need to move between sections:
- either the background/storage state should say so
- or the popup should invalidate and refetch

Not invent its own record-truth model.

---

# Strong recommendation: reduce clever optimism

Your current popup is trying to be very smart with optimistic UI.

But your own architecture doc shows something important:

> the background already owns submission orchestration and writes session state.

That means the popup does **not** need to synthesize so much optimistic truth itself.

## Better approach
For “in progress” UX:
- show `submission_batch` / `submission_state` directly
- invalidate counts and records after submit actions
- let background/storage drive the truth

This is much simpler than:
- `buildRenderableServerSections`
- `applyLastSubmitResult`
- merging submitted/failed optimistic IDs into server tabs in the popup

You may keep **lightweight optimistic display** for the banner and in-progress tab, but stop trying to maintain full optimistic tab correctness in popup memory.

---

# What to do about skip

Given your architecture and YAGNI:

## Recommended rule
Define skip as:

> “Hide this pending record in the current popup session only.”

That means:
- keep it in Zustand only
- do not write it to background/storage
- clear it when popup closes/reopens
- submit-all must use the visible pending list only

That is simple and intuitive.

---

# Contract/context handling in the simpler design

From your doc, explicit contract selection is important and context drift rules matter.

So keep the logic, but simplify ownership:

## Background / helper modules still own:
- context normalization
- contract validity rules
- entity drift handling
- group invalidation rules

## Popup only does:
- fetch current context
- fetch current contracts
- render selector
- trigger “change contract”
- invalidate relevant queries

The popup should not try to be a mini workflow engine here.

---

# Practical package fit for MV3 popup

This stack fits your extension constraints well.

## Preact
Good fit because popup is isolated and lightweight.

## TanStack Query
Works well even if your “API layer” is mostly:
- `chrome.runtime.sendMessage`
- `chrome.storage.local/session`

A query function can simply wrap those.

## Zustand
Good for tiny UI state. Don’t overuse it.

## Zod
Helpful because your message surface is broad and untyped.

---

# Suggested file structure

Keep it simple.

```txt
popup/
  main.tsx
  App.tsx

  state/
    ui-store.ts

  queries/
    bootstrap.ts
    workspace.ts
    contracts.ts
    counts.ts
    records.ts
    submission-state.ts

  mutations/
    save-token.ts
    save-settings.ts
    change-contract.ts
    submit-record.ts
    submit-batch.ts
    resume-batch.ts
    refresh-session.ts
    reset-link.ts

  lib/
    chrome-storage.ts
    chrome-messages.ts
    schemas.ts
    query-client.ts

  components/
    screens/
      SetupScreen.tsx
      ActivateScreen.tsx
      SessionExpiredScreen.tsx
      MainScreen.tsx
      SettingsScreen.tsx
      ErrorScreen.tsx

    workspace/
      SummaryCard.tsx
      ContractSelect.tsx
      SubmissionBanner.tsx
      TabBar.tsx
      RecordList.tsx
      RecordCard.tsx
      LoadMoreButton.tsx
      Toast.tsx
```

This is enough. No giant architecture needed.

---

# Data model: simplest good version

## UI store
Only:
```ts
type PopupUiState = {
  activeTab: "pending" | "inProgress" | "submitted" | "failed";
  skippedIds: number[];
  toast: { message: string; tone?: "neutral" | "error" | "success" } | null;
  setActiveTab(tab): void;
  skip(id): void;
  clearSkipped(): void;
  showToast(toast): void;
  clearToast(): void;
};
```

## Queries
```ts
bootstrap
workspaceContext
contracts
counts
records(section)
submissionState
```

## Mutations
```ts
saveToken
refreshSession
changeContract
submitRecord
submitBatch
resumeBatch
saveSettings
resetLink
```

That is enough.

---

# Query key design

Keep it predictable.

```ts
["bootstrap"]
["workspace-context"]
["contracts", entityId]
["counts", entityId, contractId]
["records", section, entityId, contractId]
["submission-state"]
```

If entity/contract changes, keys naturally shift.

That avoids lots of manual invalidation complexity.

---

# Example query behavior

## Contracts
```ts
useQuery({
  queryKey: ["contracts", entityId],
  queryFn: fetchContracts,
  staleTime: 30_000,
});
```

That replaces the custom TTL cache.

## Counts
```ts
useQuery({
  queryKey: ["counts", entityId, contractId],
  queryFn: fetchCounts,
});
```

## Records
```ts
useInfiniteQuery({
  queryKey: ["records", section, entityId, contractId],
  queryFn: fetchRecordPage,
  getNextPageParam: (lastPage) =>
    lastPage.hasMore ? lastPage.offset + lastPage.items.length : undefined,
});
```

No manual `offset/hasMore/loading/error/loaded` object needed.

---

# Mutations: simple invalidation strategy

After successful:
- submit record
- retry record
- submit batch
- resume batch
- change contract
- refresh context

invalidate:

```ts
["bootstrap"]
["workspace-context"]
["counts"]
["records"]
["submission-state"]
```

Maybe not maximally optimized, but very KISS and safe.

For a popup, that is fine.

---

# Storage reactivity

You currently rely on storage change listeners a lot. That can still work.

## Keep one listener
When relevant local/session keys change:
- invalidate queries

Example:
- if `submission_batch`, `active_submit_id`, `last_submit_result`, `submission_state` change
  - invalidate `["submission-state"]`
  - invalidate `["records"]`
  - invalidate `["counts"]`

- if contract/entity context keys change
  - invalidate `["bootstrap"]`
  - invalidate `["workspace-context"]`
  - invalidate `["contracts"]`
  - invalidate `["records"]`
  - invalidate `["counts"]`

This is much cleaner than manually calling `renderWorkspaceFromCache(...)`.

---

# What not to migrate yet

To stay YAGNI, do **not** add:

- Redux Toolkit
- XState
- entity adapters
- event bus
- custom repository layer
- RxJS
- persistent Zustand middleware
- offline support
- global form library

All unnecessary for this popup.

---

# Final recommended implementation approach

## Phase 1 — Data/cache simplification first
Before redesigning all UI:
- introduce TanStack Query
- introduce Zustand
- wrap `chrome.storage` and `chrome.runtime.sendMessage`
- replace `tabCache` / `countsState` / local snapshot state with queries

## Phase 2 — Replace imperative rendering
- move popup DOM rendering to Preact components
- keep current screens and strings

## Phase 3 — Remove special-case popup merge logic
Delete:
- `buildRenderableServerSections`
- `applyLastSubmitResult` popup patch logic
- contract TTL cache
- manual workspace load queueing
- direct DOM card builders

---

# My final opinion

Given your current architecture doc, the best KISS/YAGNI move is:

> **Do not make the popup smarter. Make it dumber.**

Let:
- background stay the orchestrator
- storage/session stay the runtime truth
- query layer handle fetching/caching
- popup render only the latest known state

That will remove most of the current UI bugs.

---

# Final checklist

## Use
- [ ] Preact
- [ ] TanStack Query
- [ ] Zustand
- [ ] Zod (recommended)

## Remove
- [ ] custom tab cache state
- [ ] custom counts cache state
- [ ] local/session snapshot caching in popup
- [ ] contract TTL cache
- [ ] render-time record patching/merging logic
- [ ] imperative screen/list rendering

## Keep simple
- [ ] background remains source of truth
- [ ] popup queries current state
- [ ] UI store only for local interaction state
- [ ] skip = local hide for current popup session
- [ ] submit-all must use visible data if skip exists

---
