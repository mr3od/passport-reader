# HISTORY

Agent-maintained log of significant changes. Each entry records what was done and who did it.

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

## 2026-03-31 — final popup proposal consolidation [codex]

- Added the canonical final popup design proposal in `docs/FINAL-DESIGN-PROPOSAL.md`
- Added the canonical final popup mock in `docs/final-design-proposal.html`
- Archived exploratory and duplicate popup proposal artifacts under `docs/archive/design-exploration/`
- Updated the final written proposal and final HTML mock to state which design artifacts are canonical versus archived
