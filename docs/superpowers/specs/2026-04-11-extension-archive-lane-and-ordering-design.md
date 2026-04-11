# Extension Archive Lane And Ordering Design

## Goal

Add a real archive workflow for agency uploads in the extension:
- archive from any record tab (except transient `inProgress`)
- unarchive from `archived`
- keep lifecycle status semantics intact
- make ordering deterministic across all tabs

## Locked Decisions

- Archive state is stored only in `uploads.archived_at`.
- Do not overload `uploads.status` with `archived`.
- Any owned record can be archived.
- `archived` tab sorting is by `archived_at` descending.
- `inProgress` ordering is queue-driven (active first, then queue order).

## Scope

In scope:
- schema change for `uploads.archived_at`
- new archive/unarchive API action
- `archived` section in records list
- extension UI actions and new archived tab
- deterministic sorting rules in popup rendering
- tests across platform, API, and extension

Out of scope:
- changing Masar submission semantics
- changing upload processing lifecycle statuses
- changing dashboard summary metrics layout
- adding archive audit history tables

## Why This Shape

`uploads.status` already models processing lifecycle (`received/processing/processed/failed`).  
Archive is a workspace visibility control, not a processing state.  
Mixing them creates brittle query logic and retry confusion.

`uploads.archived_at` keeps both dimensions separate and queryable:
- processing truth stays in `uploads.status` + latest `masar_status`
- visibility truth is `archived_at IS NULL/IS NOT NULL`

## Data Model

Add one nullable column:
- `uploads.archived_at TEXT NULL`

Behavior:
- archive => set `archived_at = now(UTC ISO)`
- unarchive => set `archived_at = NULL`

No additional column for now (`archived_by_user_id` intentionally skipped).

## Schema + Contract Updates

Because this adds an upload column, update all required schema surfaces together:

1. `passport-platform/src/passport_platform/db.py`
- `SCHEMA_SQL` includes `uploads.archived_at`
- `_upgrade_schema()` adds `ALTER TABLE uploads ADD COLUMN archived_at TEXT` when missing

2. `passport-platform/migrations/`
- add/update migration SQL with `archived_at` on `uploads`

3. `passport-platform/src/passport_platform/models/upload.py`
- add `archived_at` to `Upload` dataclass

4. `passport-platform/src/passport_platform/schemas/results.py`
- add `archived_at` to:
  - `UserRecord`
  - `UserRecordListItem`

5. `passport-platform/src/passport_platform/repositories/records.py`
- include `uploads.archived_at` in list/detail projections
- update section predicates (below)

6. `passport-api/src/passport_api/schemas.py` and routes
- expose `archived_at` in record response/list item responses
- support `section=archived`

## Section Semantics (Server Truth)

`GET /records?section=...` supports:
- `pending`
- `submitted`
- `failed`
- `archived`
- `all`

Where clauses:
- `pending`:
  - `uploads.status = 'processed'`
  - latest `ms.masar_status IS NULL`
  - `uploads.archived_at IS NULL`
- `submitted`:
  - latest `ms.masar_status = 'submitted'`
  - `uploads.archived_at IS NULL`
- `failed`:
  - (`uploads.status = 'failed'` OR latest `ms.masar_status IN ('failed','missing')`)
  - `uploads.archived_at IS NULL`
- `archived`:
  - `uploads.archived_at IS NOT NULL`
- `all`:
  - no archive filter (returns both archived and non-archived)

Counts endpoint (`/records/counts`) remains:
- `pending/submitted/failed` only
- archived rows excluded from those three counts

## Sorting Rules

Server-side list sorting:
- `pending/submitted/failed/all`: `uploads.created_at DESC, uploads.id DESC`
- `archived`: `uploads.archived_at DESC, uploads.id DESC`

Client-side rendering normalization (after optimistic merge):
- `pending/submitted/failed`: `created_at DESC`, tie-break `upload_id DESC`
- `archived`: `archived_at DESC`, fallback `created_at DESC`, tie-break `upload_id DESC`
- `inProgress`:
  - active record first
  - then remaining records in deterministic `submission_batch.queue` order
  - items not found in queue (safety fallback) sorted by `created_at DESC`

This prevents ordering regressions from optimistic replay (`last_submit_result`) and section merges.

## API Changes

### New endpoint

`PATCH /records/{upload_id}/archive`

Request body:
- `{ "archived": true }` => archive
- `{ "archived": false }` => unarchive

Response:
- updated `RecordResponse`

Validation:
- upload must belong to authenticated user
- archive (`true`) is allowed for any owned record
- unarchive (`false`) is allowed for any owned record
- operation is idempotent:
  - archive on already-archived record returns success with unchanged timestamp
  - unarchive on non-archived record returns success

## Platform Service Changes

`RecordsService` / repository responsibilities:
- repository method to toggle `uploads.archived_at`
- ensure updates are owner-scoped (`uploads.user_id = ?`)

No changes to Masar submission insert/update semantics.

## Extension UX Changes

### Tabs

- Add `archived` tab in popup:
  - label from `strings.js`
  - load-more support same as other server tabs

### Card actions

- In `pending` + `failed` + `submitted`:
  - keep selection checkbox
  - add `Archive` action button
- In `archived`:
  - add `Unarchive` action button
- In `inProgress`:
  - no archive action

### Action flow

- Popup sends runtime message to background:
  - e.g. `SET_ARCHIVE_STATE { uploadId, archived }`
- Background calls new API route
- On success:
  - refresh relevant tabs (`pending`, `submitted`, `failed`, `archived`; optionally all dirty)
  - clear removed ids from `selectedUploadIds`
  - toast success in Arabic
- On failure:
  - map auth failures to existing relink/session handling
  - show Arabic error toast

### Strings (Arabic)

Add user-facing strings to `passport-masar-extension/strings.js`:
- archived tab label
- empty archived section text
- archive action label
- unarchive action label
- archive success/failure messages
- unarchive success/failure messages

No inline literals in popup/background for agency-visible copy.

## Queue Ordering Detail

`inProgress` must reflect work execution order, not server cache precedence.

Implementation shape:
- derive `queueOrderMap` from `submission_batch.queue`
- build `inProgress` list from merged sections
- sort using:
  1. active id exact match
  2. queue index ascending
  3. fallback timestamp descending

This gives operators the true current pipeline view.

## Backward Compatibility

- Existing clients without archive actions continue working:
  - non-archived behavior remains unchanged
- existing counts contract preserved (`pending/submitted/failed`)
- no changes to token/auth/session contracts

## Risks And Mitigations

Risk:
- optimistic merge can still reorder rows unexpectedly

Mitigation:
- do not rely on append-only optimistic updates
- run explicit deterministic per-tab sorting after every merge/render pass
- keep append behavior only for server pagination fetch accumulation

Risk:
- archive endpoint creates state mismatch with lifecycle status

Mitigation:
- make archive status-agnostic and owner-scoped only

Risk:
- selected rows become hidden after archive

Mitigation:
- always reconcile `selectedUploadIds` against visible selectable ids after refresh

## Testing Plan

Platform tests:
- section filtering excludes archived rows from pending/failed/submitted
- archived section returns archived rows only
- archived section sorted by `archived_at DESC`
- archive/unarchive works regardless of lifecycle status
- unarchive restores pending/failed visibility

API tests:
- `GET /records` accepts `section=archived`
- archive patch success path
- archive patch success for submitted/non-pending records
- unarchive patch success
- response payload includes `archived_at`

Extension tests:
- archived tab included in tab store + fetch coordinator behavior
- archive/unarchive card actions send correct message
- archive action available in submitted cards and hidden in inProgress cards
- post-action selection reconciliation drops moved ids
- deterministic sorting helper tests:
  - pending/failed/submitted by `created_at DESC`
  - archived by `archived_at DESC`
  - inProgress by queue with active first
- regression test for `last_submit_result` no longer ending up at list tail

## Rollout Plan

1. Ship schema + platform + API support behind normal deployment.
2. Ship extension with archived tab/actions.
3. Verify:
- archive from pending/submitted/failed works
- unarchive restores row to correct lane
- ordering is stable in all tabs
- inProgress matches queue order during active batch

## Non-Goals (Explicit)

- no multi-user archive audit trail
- no hard-delete
- no auto-archive policies
- no change to quota/accounting logic
