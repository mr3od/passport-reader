# HISTORY

Agent-maintained log of significant changes. Each entry records what was done and who did it.

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
