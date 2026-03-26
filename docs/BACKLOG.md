# BACKLOG

Agent-friendly backlog for the `passport-reader` workspace.

This file is intended to be executable as planning input for future agents:
- prefer small, reviewable slices
- preserve package boundaries
- avoid introducing new architectural shortcuts
- update this file as priorities change

## Boundary Note

Repo boundary rules now live in [AGENTS.md](/Users/nexumind/Desktop/Github/passport-reader/AGENTS.md).
This backlog should focus on executable work, not restate policy.

## Prerequisites

### D1. Add `ARCHITECTURE.md`

**Goal**
- add a short architecture explainer that points to `AGENTS.md` for hard rules

**Must include**
- package responsibilities
- high-level data/control flow only
- no duplicated policy text from `AGENTS.md`

Do this before any other backlog item — it pays forward to every agent session.

## Highest Priority Work

### P1. Remove direct `passport-core` dependency from `passport-telegram`

Status
- Completed by `codex`
- `passport-telegram` now depends on `passport-platform` builders and result views only.

**Goal**
- `passport-telegram` depends only on `passport-platform`.

**Current problem**
- `passport-telegram` still imports `passport_core` types/builders directly.

**Required work**
- remove `passport-core` from `passport-telegram/pyproject.toml`
- stop importing `PassportWorkflow`, `CoreSettings`, and `PassportWorkflowResult` from Telegram code
- move all processing/runtime construction behind `passport-platform` builders
- expose adapter-safe processing result views from `passport-platform`

**Acceptance**
- no `passport_core` imports under `passport-telegram/src`
- no `passport-core` dependency in `passport-telegram/pyproject.toml`
- Telegram tests pass using `passport-platform` abstractions only
- `passport-telegram` does not relay through `passport-api`

### P2. Centralize runtime/service construction in `passport-platform`

Status
- Completed by `codex`
- Shared runtime builders now construct adapter services from `passport-platform`.

**Goal**
- shared builders in `passport-platform` construct runtime services for adapters

**Required work**
- add `build_platform_runtime(...)`
- add `build_processing_runtime(...)`
- export them from `passport-platform`
- refactor `passport-api` and `passport-telegram` to use these builders

**Acceptance**
- `passport-api` no longer manually constructs auth/users/records runtime pieces
- `passport-telegram` no longer manually constructs processing/runtime pieces

### P3. Split admin functionality into `passport-admin-bot`

**Goal**
- separate agency bot from admin/operator bot

**Required work**
- create new package `passport-admin-bot`
- move admin commands out of `passport-telegram`
- keep user/plan/status/reporting business logic in `passport-platform`

**Final command split**

`passport-telegram`
- `/start`
- `/help`
- `/account`
- `/usage`
- `/plan`
- `/token`
- `/masar`

`passport-admin-bot`
- `/start`
- `/help`
- `/admin`
- `/stats`
- `/recent [count]`
- `/usage <telegram_user_id>`
- `/setplan <telegram_user_id> <free|basic|pro>`
- `/block <telegram_user_id>`
- `/unblock <telegram_user_id>`

**Acceptance**
- admin code removed from `passport-telegram`
- new admin bot depends on `passport-platform` only
- no compatibility stubs required

### P4a. Add `import-linter` with currently-valid contracts

**Goal**
- prevent new boundary violations from being introduced while cleanup is in progress

**Required contracts (enforce now)**
- `passport-core` is independent from all other repo packages
- `passport-api` may not import `passport-core`

**Skip for now**
- `passport-telegram` → `passport-core` is a known violation being fixed in P1; exclude it until P1 lands

**Acceptance**
- CI fails on new invalid imports
- known P1 violation is explicitly excluded in import-linter config until resolved

### P4b. Tighten import-linter contracts after P1

**Goal**
- enforce the full boundary contract once `passport-telegram` is clean

**Required contracts (add after P1)**
- `passport-telegram` may not import `passport-core`
- `passport-admin-bot` may not import `passport-core`

**Acceptance**
- all package boundary rules in `AGENTS.md` are enforced in CI
- exclusion from P4a is removed

## Backend and Domain Refactors

### B1. Add adapter-safe processing result accessors in `passport-platform`

**Goal**
- upper layers should not need `passport-core` result types

**Required work**
- add computed/accessor properties on `TrackedProcessingResult`
- expose filename, image bytes, face crop bytes, completion flags, extracted data

**Acceptance**
- adapters format responses/messages without importing `passport-core` types

### B2. Keep `passport-platform` as the only DB/filesystem owner

**Goal**
- all artifact persistence and database interaction stays in one place

**Required work**
- audit adapters for direct persistence behavior
- move any remaining write-side ownership into `passport-platform`

### B3. Clarify sync vs async processing boundary

Deferred. The interface contract depends on queueing design. Define this when Q1 work starts — the adapter-facing API shape will follow from how `passport-platform` owns enqueue/dequeue.

### B5. Use Pydantic for new and changed boundary-facing models

**Standing rule — not a rewrite project**
- new command objects, public result/DTO objects, API schemas, and config/settings use Pydantic
- internal dataclasses and simple objects do not need to be changed
- no mass rewrite required; apply on contact

## Queueing and Workers

### Q1. Introduce queueing only inside `passport-platform`

**Important rule**
- `passport-core` must not know about queues, brokers, job IDs, retries, or persistence

**Correct model**
- `passport-platform` owns enqueue/dequeue/retries/status
- worker calls `passport-core` in-memory

**Recommended off-the-shelf option**
- prefer a simple queue like RQ first
- avoid writing a custom queue/worker system

**Not allowed**
- `passport-core` directly talking to Redis/SQS/DB queues
- queue semantics leaking into `passport-core`

### Q2. Define job schema for background processing

**Future task**
- define upload-processing job payloads
- define job status lifecycle
- define retry/idempotency rules

**Suggested lifecycle**
- queued
- processing
- succeeded
- failed

## Analytics and Observability

### O1. Separate observability from analytics

**Rule**
- observability != product analytics

**Recommended tools**
- Sentry for errors/traces/operational debugging
- PostHog for agency/product analytics

### O2. Introduce product analytics without abusing `usage_ledger`

**Goal**
- keep quota accounting separate from behavioral analytics

**Recommended work**
- keep `usage_ledger` for quota/billing semantics only
- add a separate analytics event layer later if needed

### O3. Define agency-level analytics model

**Suggested dimensions**
- active agencies
- uploads per agency
- processing success/failure funnel
- Masar submission funnel
- quota hits by plan

## Off-the-Shelf Tooling Opportunities

### T1. Use `import-linter` for dependency boundaries

**Why**
- better fit than ad hoc scripts
- better fit than `ty`
- more suitable than relying only on `ruff`

### T2. Use RQ before considering Celery

**Why**
- simpler fit if background processing is introduced
- enough for straightforward queued jobs

### T3. Keep `ruff` and `ty` for what they are good at

**Use**
- `ruff`: linting and local import hygiene
- `ty`: type checking

**Do not use as primary architecture enforcement**

## Documentation Work

### D2. Update package READMEs after the split

**Required**
- `passport-telegram/README.md` becomes agency-only
- `passport-admin-bot/README.md` documents admin-only behavior
- `passport-platform/README.md` describes itself as the orchestration boundary

## Later Track

Work in this section is valid but should not be started until the triggers are met.

### B4. Modernize persistence in `passport-platform`

**Triggers — start only when one of these is true**
- schema changes become frequent enough that `_upgrade_schema()` is painful to maintain
- joins or query complexity grows materially
- multiple services or processes need coordinated DB evolution
- manual SQL row-mapping becomes a recurring maintenance cost

**Goal**
- move `passport-platform` to a more maintainable DB/migration stack

**Required work**
- adopt Alembic as the single migration mechanism
- replace runtime schema upgrade logic with explicit versioned migrations
- migrate repository/database interaction to SQLAlchemy
- keep all DB code inside `passport-platform`

**Acceptance**
- schema changes are managed through Alembic migrations
- ad hoc runtime schema upgrade logic is removed or reduced to bootstrap-only concerns
- database access in `passport-platform` goes through SQLAlchemy-based models/session patterns

## Suggested Execution Order

1. Add `ARCHITECTURE.md` (D1 — prerequisite)
2. Add `import-linter` with safe contracts only (P4a)
3. Add `passport-platform` runtime builders (P2)
4. Remove direct `passport-core` dependency from `passport-telegram` (P1)
5. Tighten import-linter contracts (P4b)
6. Add adapter-safe processing result accessors in `passport-platform` (B1)
7. Refactor `passport-api` and `passport-telegram` to consume `passport-platform` only
8. Split out `passport-admin-bot` (P3)
9. Update package READMEs (D2)
10. Add observability/analytics tooling (O1–O3)
11. Introduce queueing only inside `passport-platform`, if still needed (Q1–Q2)
12. Modernize persistence if triggers are met (B4)

## Notes for Future Agents

- Do not add new direct imports from adapters to `passport-core`
- Do not add DB access outside `passport-platform`
- Do not move queue infrastructure into `passport-core`
- Prefer small, boundary-enforcing refactors before feature work
- When in doubt, choose the option that strengthens package isolation
