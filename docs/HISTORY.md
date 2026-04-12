# HISTORY

Agent-maintained log of significant changes. Each entry records what was done and who did it.

## 2026-04-12 — extension archive lane follow-up, result-banner removal, and version bump [codex]

- Removed the popup result-banner layer from `passport-masar-extension/popup.js`:
  - dropped both submit and archive completion banners
  - kept the in-progress submission banner intact
  - removed the related storage-listener wiring and test exports tied only to dismissible result banners
- Updated `passport-masar-extension/tests/popup.test.js` to assert the result-banner helper is gone instead of testing banner copy/state
- Bumped the browser extension manifest version in `passport-masar-extension/manifest.json` from `1.2.0` to `1.3`
- This commit also includes the broader uncommitted extension archive/selection workflow changes plus the platform seed/submitted-ordering updates already present in the worktree
- Verification:
  - Ran `rtk node --test passport-masar-extension/tests/popup.test.js passport-masar-extension/tests/background.test.js`
  - Result: extension popup/background tests passing (`91 passed, 0 failed`)

## 2026-04-12 — extension selection/archive workflow hardening and seed restore support [kite]

- Reworked the extension popup selection flow in `passport-masar-extension/popup.js`, `popup.html`, `popup.css`, and `strings.js`:
  - pending and failed cards are selectable directly from the list
  - the queue header now exposes a loaded-only “mark all” action plus a selected-action menu for submit vs archive
  - the main CTA now reflects selected-count state instead of broad submit-all wording
  - archive completion can render its own dismissible result banner, with submit results still taking priority
  - the settings phone input now caps input length with `maxlength="14"`
- Split archive execution onto its own background/session lane in `passport-masar-extension/background.js`:
  - renamed runtime submit storage from `submission_batch` to `submit_batch`
  - added `archive_batch`, `active_archive_id`, and `last_archive_result`
  - routed archive work through `ARCHIVE_BATCH`, preserved relink behavior on backend-auth failure, and removed the dead `SET_ARCHIVE_STATE` message branch
- Tightened optimistic state handling across the extension:
  - `passport-masar-extension/queue-filter.js` now treats optimistic `archived` results as removed from pending/failed rendering
  - popup optimistic merging now includes archive batch results so archived rows disappear before the forced reload
  - `passport-masar-extension/context-change.js` now uses consistent `submit*` helper naming while keeping the stored key `submit_batch_context`
  - `passport-masar-extension/background.js` now preserves the full submit queue and accumulated results on every mid-drain `submit_batch` write
- Updated regression coverage in `passport-masar-extension/tests/background.test.js`, `popup.test.js`, and `tab-data-store.test.js` for archive auth propagation, archive result banners, archive-aware batch-running state, loaded-only selection copy, and the renamed submit batch keys
- Updated repository support files outside the extension:
  - `passport-platform/src/passport_platform/repositories/records.py` now orders submitted records by latest Masar submission time before falling back to upload creation time
  - `passport-platform/src/passport_platform/management/seed.py` now restores archived benchmark uploads on rerun instead of leaving them skipped forever
- Verification:
  - Ran `rtk node --test passport-masar-extension/tests/*.test.js`
  - Result: extension tests passing (`133 passed, 0 failed`)
  - Ran `rtk uv run pytest passport-platform/tests/test_seed_management.py -q`
  - Result: seed management tests passing (`2 passed`)

## 2026-04-11 — records archive lane and archive toggle API/platform support [codex]

- Added upload-level archiving support in `passport-platform`:
  - new nullable `uploads.archived_at` column in schema/migrations
  - startup migration in `db.py` to backfill the column/index on existing databases
  - new index `idx_uploads_user_archived_at_id_desc` for archived section ordering
  - repository/service support for idempotent owner-scoped archive toggling
- Updated record section semantics and ordering in platform repositories:
  - `pending`, `submitted`, and `failed` now exclude archived rows
  - new `archived` section includes rows where `archived_at IS NOT NULL`
  - archived section ordering is `archived_at DESC, id DESC`
  - submit-eligible query now excludes archived rows
- Extended API contracts for archive workflows:
  - `GET /records` now accepts `section=archived`
  - added `PATCH /records/{upload_id}/archive` with `{ "archived": boolean }`
  - `RecordResponse` and `RecordListItemResponse` now expose `archived_at`
- Updated API/platform docs and tests to cover archive semantics and idempotent archive/unarchive behavior.
- Verification:
  - Ran `uv run ruff check passport-platform/src/passport_platform passport-platform/tests passport-api/src/passport_api passport-api/tests`
  - Ran `uv run ty check passport-platform/src/passport_platform passport-api/src/passport_api`
  - Ran `uv run pytest passport-platform/tests/test_records_service.py passport-api/tests/test_api.py`

## 2026-04-09 — extension last-submit optimistic overlay restored [codex]

- Fixed `passport-masar-extension/popup.js` so `renderWorkspaceFromCache` routes server tab items through `buildRenderableServerSections(...)` again instead of bypassing the `last_submit_result` optimistic overlay
- Restored immediate section movement after submit without waiting for the next tab fetch
- Verification:
  - Ran `node --test passport-masar-extension/tests/popup.test.js`
  - Ran grep checks confirming the inline `serverSections = { ... }` block is gone and `buildRenderableServerSections(...)` is called from `renderWorkspaceFromCache`

## 2026-04-09 — extension tab display/coordinator split and load-more restoration [codex]

- Replaced popup tab cache state with two pure modules in `passport-masar-extension`: `tab-data-store.js` for per-tab display data and `tab-fetch-coordinator.js` for per-tab fetch status, dirty flags, and request IDs
- Kept `inProgress` out of stored tab state entirely and continued deriving it only in `popup.js` through `QueueFilter.mergeOptimisticSections`
- Reworked popup tab loading to use request-scoped coordinator commits, stale-response rejection, tab invalidation via `markAllDirty`, and paginated append behavior for pending, submitted, and failed tabs
- Restored load-more controls in `passport-masar-extension/popup.html`, wired their Arabic button copy and click handlers in `popup.js`, and fixed pagination `hasMore` behavior to derive from page size instead of trusting missing backend metadata
- Added focused extension tests for the new pure modules in:
  - `passport-masar-extension/tests/tab-data-store.test.js`
  - `passport-masar-extension/tests/tab-fetch-coordinator.test.js`
- Verification:
  - Ran `node --test passport-masar-extension/tests/*.test.js`
  - Ran grep checks for removed `tabCache` usage, absent `response.data?.hasMore`, absent `button.hidden`, and expected load-more wiring in popup HTML/JS
  - Result: extension tests passing (`126 passed, 0 failed`)

## 2026-04-09 — extension deterministic queue phase, selection-first submit flow, and stale-code cleanup [codex]

- Migrated extension batch execution to a deterministic queue model in `passport-masar-extension/background.js`:
  - canonical batch shape is now `queue`, `active_id`, `results`, `blocked_reason`, `started_at`, `updated_at`
  - removed legacy discovery/state helpers (`appendDiscoveredIds`, `advanceSubmissionBatch`, `isRichSubmissionBatch`, `ensureSubmissionSessionConsistency`)
  - removed `SUBMIT_RECORD` runtime entrypoint; `SUBMIT_BATCH` is the only submission path
  - kept resume semantics strict (`SUBMIT_BATCH([])` resumes only when persisted batch has `active_id`)
  - hardened invalid batch-shape cleanup to clear only batch pointers (`submission_batch`, `active_submit_id`) without destructive full-state reset
  - normalized submission queue IDs to numeric form and removed mixed-ID writes in `results`

- Migrated optimistic queue derivation in `passport-masar-extension/queue-filter.js` to deterministic batch semantics only:
  - derive `submittedIds`, `failedIds`, `inProgressIds`, `activeId` from `queue + results`
  - keep precedence behavior that prefers fresher submitted/failed cache over stale pending cache
  - normalized queue/active IDs to numeric form for consistent `Set` membership

- Refactored popup submission UX in `passport-masar-extension/popup.js` and related UI files:
  - selection-driven submit flow (`selectedUploadIds`) across pending + failed records
  - single visible action button (`submit-all-btn` label now “رفع المحدد (N)”) with strict clear-on-success (`ok === true && queued === true`)
  - `submitBatch` no longer sends dead payload fields (`sourceTotal`, `nextOffset`)
  - kept reconciliation guard (`selected ∩ selectable`) to prevent ghost selections
  - kept optimistic merge/resume behavior aligned with background deterministic queue state

- Updated extension copy and styling:
  - reworded submit CTA/confirm text in `passport-masar-extension/strings.js` for selection-driven behavior
  - added selection checkbox styling in `passport-masar-extension/popup.css`
  - removed stale, unused action strings tied to deleted per-card flows (`ACTION_SUBMIT`, `ACTION_RETRY`)

- Removed stale runtime UI artifacts that were no longer functional:
  - removed dead load-more controls from `passport-masar-extension/popup.html`
  - removed dead load-more rendering/wiring from `passport-masar-extension/popup.js`
  - removed dead load-more style block from `passport-masar-extension/popup.css`
  - removed unused `notifyComplete` parameter from `drainSubmissionBatch` signature in `background.js`
  - intentionally kept `passport-masar-extension/reviewer-agent-prompt.md` unchanged

- Updated extension tests to match the deterministic model and current runtime contracts:
  - `passport-masar-extension/tests/background.test.js`
  - `passport-masar-extension/tests/popup.test.js`
  - `passport-masar-extension/tests/queue-filter.test.js`
  - coverage now asserts deterministic batch shape, unsupported `SUBMIT_RECORD`, queue/results-based banner behavior, and updated optimistic section normalization

- Verification:
  - Ran `node --test passport-masar-extension/tests/*.test.js`
  - Result: all extension tests passing (`117 passed, 0 failed`)

## 2026-04-09 — truthful submit-all scope and `/records/ids` deprecation [codex]

- Removed extension runtime usage of `FETCH_SUBMIT_ELIGIBLE_IDS` and `/records/ids` so batch submission now uses only the IDs already selected/visible to the user
- Stopped background batch auto-discovery of extra IDs during drain, preventing submitted count drift beyond user-confirmed scope
- Updated Arabic user-facing copy from broad “submit all” wording to “submit shown records” language in the popup button and confirmation message
- Marked `GET /records/ids` as deprecated in FastAPI route metadata and added an OpenAPI regression test that asserts the deprecated flag

## 2026-04-09 — extension tab empty-note visibility fix [codex]

- Fixed the shared workspace empty-note subtitle so populated tabs no longer show empty-state Arabic copy above real records
- Added a popup helper that derives the empty subtitle from the active section data instead of the tab name alone
- Added regression coverage for both populated and empty tab subtitle behavior

## 2026-04-09 — extension pre-release raw failure note gate [codex]

- Added an explicit `PRE_RELEASE_SHOW_RAW_FAILURES` path in the popup instead of leaving raw failed-note rendering as an implicit permanent behavior
- Kept raw `failure_reason_text` visible only for failed cards in pre-release mode while preserving queued and active retry labels during in-progress retries
- Added popup regression coverage proving the raw-note path is intentionally gated and does not override retry-state messaging

## 2026-04-09 — extension retry in-progress card state fix [codex]

- Fixed retried failed records rendering as failed cards inside the in-progress tab
- Changed popup/status precedence so optimistic queued or active retry state overrides stale persisted `failed` status while a retry is underway
- Added regression coverage for queued retry labels, colors, and note text so in-progress cards no longer reuse stale failure styling

## 2026-04-09 — extension stale test cleanup and popup note simplification [codex]

- Removed stale group-era extension test expectations that no longer match the contract-only workflow
- Updated background and context-change tests to stop asserting deleted `submission_group_*` state
- Simplified popup failure-note rendering so raw backend failure text no longer gets remapped in `popup.js`
- Kept scan/image failure classification in the background flow as the single source of truth

## 2026-04-09 — extension contract-only cleanup, async hardening, and retry/auth fixes [codex]

- Removed the remaining group-selection and group-fetching logic from the live extension flow, including popup state, background handlers, context fields, and related strings/tests
- Deleted dead badge/notification modules and their tests; cleaned extension docs so they describe the current runtime instead of removed codepaths
- Hardened popup async behavior with request/load IDs, debounced session re-renders, queued submit semantics, and stale-cache precedence so fresher submitted/failed data wins over stale pending data
- Updated background/popup submit handling to treat `SUBMIT_RECORD` and `SUBMIT_BATCH` as queued operations, not synchronous completion
- Restored the Masar attachment upload step in the submission flow and kept the disclosure-form `Status === false` failure check
- Removed the fake `pending` Masar submission status from the API validation path and extension retry eligibility checks; retries now start from the real latest persisted `failed` or `missing` state
- Preserved structured contract-fetch failure metadata through `contract-select.js` and popup failure routing so `GetContractList` auth failures can render the Masar login UI instead of a raw `contracts 401` error
- Updated extension/API/platform docs and extension AGENTS guidance to reflect the real `pending`, `failed`, and `missing` state model, and added focused regression coverage for retry/auth propagation and stale pending-vs-submitted cache precedence

## 2026-04-07 - removed all optimistic count logic and server count caching [mr3od]

1. Counts are always derived from tab cache sections - no more complex merging logic
2. Removed buildOptimisticCounts - eliminated the double-counting bug source
3. Removed countsState - no more stale/loading state tracking
4. Removed loadCounts API call - one less network request
5. Simplified renderWorkspaceFromCache - counts = section lengths, period


## 2026-04-07 — extension submission flow simplified [kiro]

- Removed step 4 (Attachment/Upload) from Masar submission flow
- vaccinationPictureId and vaccinationPicture now set to null
- Updated step numbers from 6 to 5 total steps
- Removed unused ERR_UPLOAD_ATTACH and ERR_UPLOAD_NO_DATA strings

## 2026-04-07 — extension UI counts double-counting fix [kiro]

- Fixed bug where UI counts showed inflated numbers during active submission
- Server counts refreshed during batch were being adjusted with batch state,
  causing double-counting (e.g., showing 100+ when API returns 60)
- Now uses tab cache section lengths during active batch instead of optimistic adjustments

## 2026-04-07 — extension submit button gating fix [kiro]

- Fixed bug where submit/retry buttons were clickable when no contract was selected
- Added `masar_contract_id` check to `canSubmit` logic in `renderWorkspaceFromCache`
- Buttons now correctly disable when contract is missing, expired, or inactive

## 2026-04-07 — extension failed record retry fix [kiro]

- Fixed bug where failed passport card retry did not submit to Masar and the record was swallowed (not showing in any section)
- Removed batch record pre-fetching in `buildRecordLookup` — now fetches only the currently processing record
- Fixed retry flow so failed and missing records are retried from their real persisted state
- Kept `pending` as a derived workspace lane (`uploads.status = processed` plus no Masar row), not a persisted Masar submission status
- Added regression coverage that rejects fake `pending` retry state

## 2026-04-06 — extension submission hardening and contact defaults nudge [claude]

- Fixed submission banner math: exposed `failed_ids` count in the progress detail line so all numbers add up (`done/total • N فشل`)
- Surfaced raw Masar `traceError` from all 6 submission steps and on the HTTP 200 + `Status: false` paths in steps 5 and 6
- Simplified `buildFailureReason` to always store the raw trace text instead of silently discarding it for classified failure kinds
- Capped `mapNameTokens` at 3 tokens to stop joining middle name tokens into `secondName`, which was causing Masar 400 errors when names exceeded 15 characters
- Removed the context-change banner and its confirm/defer flow from popup and HTML; stale UI updates now handled by the storage listener
- Removed dead `fetchAllRecords`, `updateBadge`, `countFailedRecords` paths and their message handlers
- Replaced per-fetch `session_expired` writes and per-success `session_expired: false` resets with a single 401 side-effect path in `apiFetch`; cleared `session_expired` atomically with new token writes to fix badge staying red after relink
- Normalised all `chrome.storage` access through `localGet`/`localSet`/`localRemove` helpers; removed raw callback-based `chrome.storage.local.get` calls
- Added `chrome.storage.session.onChanged` listener in the popup to re-render the submission banner and auto-advance to `main` when in-progress drains — replacing the stale open/close refresh cycle; guarded by `state.currentScreen` to prevent pulling the user away from settings
- Replaced the `؟` help button with a Telegram contact link pointing to `t.me/mr3od`
- Added `SETTINGS_CONTACT_HINT_*` explanation in the settings screen above the contact fields, explaining that missing email/phone causes Nusuk to mark submissions as "غير مكتمل"
- Added a main-workspace nudge banner that appears when `agency_email` and `agency_phone` are both unset, with an "إعداد الآن" button that opens settings
- Changed default country code from 966 to 967 (Yemen)

## 2026-04-06 — admin-to-agency Telegram broadcasts [codex]

- Added a platform-backed broadcast queue for text and photo notifications, including artifact storage for admin-uploaded images
- Added an admin-only `/broadcast` command for text messages and reply-to-photo broadcasts
- Added an agency-bot background worker that claims queued broadcasts and fans them out to active Telegram users
- Added focused platform, admin bot, and agency bot tests covering queue creation, user targeting, and delivery behavior

## 2026-04-05 — benchmark seed management command [mr3od]

- Added `passport-platform/management/seed.py` — a repeatable seed command that loads benchmark passport cases into the platform DB for admin users; already-imported cases are skipped on re-runs so the command is safe to call repeatedly
- Added `k8s/seed-job.yaml` so the seed can be run as a one-off Kubernetes Job in the production cluster; the Job mounts the benchmark-cases PVC and targets only existing Telegram admin users
- Fixed the seed Job container entrypoint to use `python -m` invocation to avoid a broken shebang after non-editable installation
- Renamed the k8s Job resource to `passport-platform-seed` for consistency with other k8s resource names
- Added `feat(seed): reset masar submissions on each run` so benchmark seeding always starts from a clean submission state
- Added seeder instructions to `passport-platform` README

## 2026-04-03 — records counts/ids API, popup redesign, and CI unification [codex]

- Added `UserRecordListItem` and section-partitioned platform queries to `passport-platform` (pending, in-progress, submitted, failed) including submission context fields and failure reason text
- Added `GET /records/counts` and `GET /records/ids` to `passport-api` so the extension can fetch lightweight record metadata without pulling full record payloads; updated API schemas and tests
- Added section-aware background fetchers in the extension that pull counts and id lists on demand and cache results in `chrome.storage.local`, reducing full-list API calls during popup rendering
- Added a tabbed popup records cache layer so the popup reads from cached section data rather than making API calls on every open; updated `queue-filter.js` to partition from the cache
- Redesigned passport cards in the popup: pending cards show passport thumbnail, name, and nationality; submitted/failed cards carry Masar status badges; added card-level strings to `strings.js`
- Added optimistic batch-resume state so the popup shows a resuming batch immediately without waiting for a background confirmation round-trip
- Unified extension CI: merged the separate extension CI workflow into the extension-release workflow and removed the now-redundant standalone CI workflow file

## 2026-04-03 — Masar session workflow hardening [codex]

- Removed the dead passive content-script capture path from `passport-masar-extension` and consolidated runtime policy around explicit session sync and resolver-driven context transitions
- Hardened Masar token selection, contract resolution, details reopening, banner/dropdown behavior, and resume-batch error handling in the extension popup/background flow
- Added extension architecture and package guidance updates in `docs/EXTENSION.md` and `passport-masar-extension/AGENTS.md`
- Fixed `passport-platform` failed-section scoping so failed/missing records remain user-scoped and aligned the API docs/tests with the current record section semantics

## 2026-03-31 — submission stability follow-up and record lookup optimization [codex]

- Added `GET /records/{upload_id}` to `passport-api` so extension flows can fetch a specific record without reloading the full `/records?limit=200` list
- Updated extension background batch lookup to fetch records by `upload_id` instead of full-list pulls during submission loops
- Hardened popup session sync by requiring a valid session signal (`entityId` or `jwt`) before clearing `session_expired` / `submit_auth_required`
- Added and updated tests to cover single-record API retrieval and session-sync signal validation

## 2026-03-31 — extension UI redesign and Masar detail tracking [codex]

- Added `masar_detail_id` to platform persistence, records projections, API schemas, and Masar status updates so submitted records can open the Nusuk detail page directly
- Removed the pre-submit `needs_review` gate so review-needed records can still be submitted and carry an amber review badge after submission
- Rebuilt the extension popup into a tabbed workspace with Pending, In Progress, Submitted, and Failed sections, centralized Arabic strings, contract selection, and home summary counters
- Added extension-side batch submission state in `chrome.storage.session`, context-change buffering, badge priority handling, and Chrome notifications for batch completion and pending context changes
- Added focused extension tests for status mapping, queue partitioning, badge logic, contract selection, popup helpers, notification titles, and batch failure propagation

## 2026-03-31 — telegram global inflight limiter and batch hardening [codex]

- Changed Telegram upload throttling to global-only inflight control; removed per-user inflight limiter state and settings.
- Kept chunked batch processing and overload handling with Arabic busy messaging for safer MVP behavior under load.
- Added regression coverage for limiter cancellation safety and global-cap behavior.
- Updated Telegram env templates, package README, and package AGENTS guidance to reflect current runtime knobs and removed stale Telegram per-user limiter env docs.

## 2026-03-31 — final popup proposal consolidation [codex]

- Added the final popup written proposal artifact that guided the redesign before implementation cleanup
- Added the canonical final popup mock in `docs/final-design-proposal.html`
- Archived exploratory and duplicate popup proposal artifacts under `docs/archive/design-exploration/`
- Updated the final written proposal and final HTML mock to state which design artifacts are canonical versus archived

## 2026-03-30 — split extension relink and login UI [codex]

- Split extension auth failures into relink-required versus login-required paths so revoked backend sessions no longer send agencies to the external login screen
- Added a popup-side failure classifier plus focused tests to map backend-auth and provider-auth failures to the correct UI state
- Updated popup copy to keep relink guidance in setup and the external-login screen focused on opening the login page

## 2026-03-30 — revoke extension sessions on re-link [codex]

- Removed `expires_at` from extension-session storage, platform models, API responses, and extension popup state so extension auth is revocation-based instead of time-based
- Updated `/auth/exchange` to revoke all existing extension sessions for the user before issuing the new session token, making the newest extension login authoritative
- Removed the unused `/auth/dev-token` endpoint and its related API config/service helpers
- Updated platform and API tests to prove a second exchange invalidates the first bearer token immediately
- Updated the extension auth helper and popup flow to persist only `api_token` and to treat backend `401` responses, not generic `403` responses, as relink-required state

## 2026-03-29 — /extension command and GitHub Releases distribution [codex]

**passport-telegram 0.3.0**
- Added `/extension` command to the agency Telegram bot; sends the Chrome extension ZIP as a document followed by 3 installation step screenshots with Arabic captions
- Extension ZIP is fetched at runtime from GitHub Releases using the `extension-latest` mutable tag; a 5-minute TTL cache in `extension.py` avoids hammering the GitHub API
- Added `PASSPORT_GITHUB_RELEASE_READ_TOKEN` and `PASSPORT_GITHUB_REPO` env vars to `TelegramSettings` for GitHub Releases access
- Added a terser-based build script that minifies and obfuscates the Chrome extension before packaging it as a ZIP artifact
- Added CI workflow to build and publish extension ZIPs to GitHub Releases on the `extension-latest` mutable channel

## 2026-03-29 — extension token exchange fix [codex]

- Fixed the extension login flow to exchange Telegram one-time tokens through `/auth/exchange` before storing the API session token
- Added a session-expired fallback in the popup when the stored extension session is no longer valid
- Put the Telegram bot login token on its own line so it is easier to copy into the extension
- Clarified the Telegram extension install steps to tell users to unzip the downloaded file before choosing `Load unpacked`
- Loaded the extension API config into the popup so the new token exchange flow can resolve the production API base URL

## 2026-03-29 — manual extension workflow triggers [codex]

- Added `workflow_dispatch` to the extension CI and extension release workflows so they can be run manually from GitHub Actions

## 2026-03-29 — deploy image propagation and bot rollout fix [codex]

- Passed the computed deploy image into the remote SSH shell so MicroK8s rollouts no longer fail on an unset `IMMUTABLE_IMAGE`
- Switched the agency Telegram deployment to `Recreate` so rollout does not briefly run two polling bot pods against the same token
- Switched the admin Telegram deployment to `Recreate` for the same single-poller rollout behavior

## 2026-03-29 — nodeport registry deploy tunnel [codex]

- Updated CI deploys to push images through an SSH tunnel to the private MicroK8s `localhost:32000` registry NodePort
- Removed the external registry login/push path from the deploy workflow so production deploys no longer depend on the Cloudflare-fronted registry hostname

## 2026-03-28 — switch deploys to immutable registry images [codex]

- Updated the deploy workflow to build and push immutable registry-tagged images in CI instead of building and importing images on the MicroK8s server
- Applied manifests with the registry-backed `latest` image and then rolled API, Telegram, and admin-bot deployments to the exact immutable image tag for the current deploy
- Removed the temporary server-side local-image rendering workaround in favor of the registry-based rollout model
- Updated the workflow to read registry credentials from the configured `REGISTRY_USERNAME` and `REGISTRY_PASSWORD` repository secrets and to fail with an explicit message when they are missing
- Moved SSH setup ahead of registry login so the deployment verification step can still connect to the server after an earlier workflow failure

## 2026-03-28 — switch extension API endpoint to production [codex]

- Updated `passport-masar-extension/config.js` to use `https://passport-api.mr3od.dev` as the active API base URL

## 2026-03-28 — add import-linter boundary enforcement [codex]

- Added root `import-linter` configuration for current package boundaries and allowed `passport-benchmark` to keep importing `passport-core`
- Added a CI import-boundary check to the GitHub Actions checks workflow and enforced the committed `uv.lock` during CI sync
- Updated root docs and agent guidance to include `uv run lint-imports` in the shared workspace workflow
- Updated backlog status for the import-linter tasks to reflect the current repo state

## 2026-03-28 — split admin Telegram functionality into `passport-admin-bot` [codex]

- Added a new `passport-admin-bot` workspace package with admin-only Telegram commands, English operator-facing bot copy, package-local tests, README, and AGENTS guidance
- Removed admin commands, admin config, and chat allowlist behavior from `passport-telegram` so the agency bot is strictly self-service only
- Kept agency-visible Arabic Telegram copy local to `passport-telegram/messages.py` and documented the adapter-specific string ownership rules in the root and package AGENTS files
- Added root env, Docker, Kubernetes, CI deploy, workspace, and lockfile wiring for the new admin bot deployment
- Bumped `passport-telegram` to `0.2.0`

## 2026-03-27 — container packaging and deploy import fix [codex]

- Changed the production image build to install workspace packages as non-editable so runtime containers do not depend on source trees copied from the builder stage
- Added an image import verification step in the MicroK8s deploy workflow after `microk8s images import`
- Added cleanup of the stale `passport-telegram-bot` deployment during rollout
- Set Kubernetes `imagePullPolicy: Never` for API and Telegram so MicroK8s uses the locally imported image instead of attempting a registry pull

## 2026-03-27 — passport-core v1 API removal [codex]

- Removed the legacy `passport_core.workflow`, `passport_core.llm`, and `passport_core.models` modules from `passport-core`
- Promoted the still-supported vision datamodels into `passport_core.vision_models`
- Updated `passport-core` docs and package exports to reflect the v2-only extraction API
- Bumped `passport-core` to `0.3.0`

## 2026-03-27 — ingress deployment hardening [codex]

- Disabled FastAPI debug mode before public exposure through the API Ingress
- Switched API readiness and liveness probes from raw TCP checks to HTTP `/health`
- Added cert-manager rollout waits in the deploy workflow before applying the `ClusterIssuer`

## 2026-03-27 — MicroK8s ingress and cert-manager exposure for API [codex]

- Added a production `ClusterIssuer` for Let's Encrypt using cert-manager and the MicroK8s `public` ingress class
- Added an API Ingress for `passport-api.mr3od.dev` with TLS managed by cert-manager
- Updated the deploy workflow to enable the MicroK8s `ingress` and `cert-manager` addons before applying manifests
- Extended deployment verification to report ingress and certificate resources after rollout

## 2026-03-27 — runtime contract consolidation for MicroK8s [codex]

- Added one root `.env.example` for local development and removed duplicate package env examples
- Switched API and Telegram env-file defaults to the root `.env` contract
- Added versioned production manifests under `k8s/` for namespace, PVC, API, and Telegram deployments
- Consolidated to one root Docker build path and removed local Compose plus the Telegram-specific Dockerfile
- Simplified deployment to a declarative-first GitHub Actions MicroK8s flow based on applying `k8s/` manifests
- Updated package READMEs to document host-based `uv run ...` development from the workspace root

## 2026-03-27 — cross-package pytest collection fix [codex]

- Renamed the Telegram config test module to avoid duplicate `test_config.py` collection collisions in root workspace pytest runs
- Verified combined pytest collection now passes without requiring `--import-mode=importlib`

## 2026-03-27 — root workspace packaging and env cleanup [codex]

- Added a root-managed `uv` workspace with a shared lockfile, shared tooling config, and shared dev dependency group
- Excluded experimental `browser-session` from the maintained workspace path
- Reduced maintained package manifests to thin distribution metadata while preserving separate package identities
- Updated maintained package READMEs to teach a root-first workspace workflow
- Removed stale environment variables and unused config fields from production examples and package settings
- Added workspace design and implementation plan docs under `docs/superpowers/`

## 2026-03-24 — MRZ validator hardening and benchmark test cleanup [codex]

- Tightened TD3 MRZ line 2 validation to require exact length and required check digits
- Added direct `passport-core` MRZ tests for missing check digits and malformed line lengths
- Removed stale `passport-benchmark` tests that still imported deleted compatibility modules

- Consolidated on the root `.env` / `.env.production` contract and removed adapter env-file indirection from API, Telegram, and shared runtime builders
- Updated root and package docs to describe the workspace-first `uv` workflow, root `pyproject.toml`, root tooling (`ruff`, `pytest`, `ty`), and MicroK8s `k8s/` deployment path
- Tightened test fixtures and workspace `ty` configuration so `uv run ty check` passes while excluding the experimental `browser-session` package

## 2026-03-24 — upstream runtime boundary cleanup [codex]

- Added shared `passport-platform` runtime builders for adapters
- Added adapter-safe extracted-data/result accessors on `TrackedProcessingResult`
- Refactored `passport-api` to build services through `passport-platform`
- Refactored `passport-telegram` to use `passport-platform` only and removed its direct `passport-core` dependency
- Updated backlog and package READMEs to reflect completed P1/P2 runtime boundary work

## 2026-03-24 — prompt and token validation updates [codex]

- Added prompt design notes in `docs/PROMPT-DESIGN.md`
- Refined the extraction prompt for two-page spreads and Arabic token spacing
- Corrected benchmark expectations for `case_038`
- Added warning-only validation for Arabic/English given-name token counts outside the 3-4 range
- Added benchmark coverage for the new token-count validation warnings

## 2026-03-24 — v2 extraction migration [claude]

**passport-core 0.2.0**
- Added `extraction/` subpackage: extractor, prompt, models, normalize, validate, confidence
- Added `mrz/` subpackage: TD3 parser, check digits, line building
- Deprecated v1 modules (`workflow.py`, `llm.py`, `models.py`) with `DeprecationWarning`
- Removed `benchmark.py` and its tests
- Removed dead `passport-benchmark` script entry from pyproject.toml

**passport-benchmark 0.2.0**
- Removed experiment code (`extractor_v2.py`, `prompt_v2.py`, `mrz.py`, `run_v1_extractor.py`)
- Updated imports to use `passport_core.extraction` and `passport_core.mrz`
- Updated README and added AGENTS.md

**Root**
- Added extraction pipeline, code quality, and pre-commit checklist rules to AGENTS.md
- Added AGENTS.md to both packages

**Benchmark results**
- v1 workflow: 94.9% accuracy
- v2 extraction: 98.1% accuracy (+3.2pp)
- Model: `google/gemini-3.1-flash-lite-preview`
