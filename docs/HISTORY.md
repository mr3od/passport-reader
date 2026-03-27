# HISTORY

Agent-maintained log of significant changes. Each entry records what was done and who did it.

## 2026-03-27 — container packaging and deploy import fix [codex]

- Changed the production image build to install workspace packages as non-editable so runtime containers do not depend on source trees copied from the builder stage
- Added an image import verification step in the MicroK8s deploy workflow after `microk8s images import`
- Added cleanup of the stale `passport-telegram-bot` deployment during rollout

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
