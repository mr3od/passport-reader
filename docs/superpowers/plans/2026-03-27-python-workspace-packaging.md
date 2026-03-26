# Python Workspace Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the repo into a reliable root-managed `uv` workspace for the maintained Python packages while preserving `passport-core`, `passport-platform`, `passport-api`, `passport-telegram`, and `passport-benchmark` as separate installable distributions.

**Architecture:** Keep the existing package directories and `src/` layouts intact. Make the root `pyproject.toml` the authority for workspace membership, shared tooling, and shared dev groups, while shrinking each maintained package manifest to distribution-specific metadata only. Exclude `browser-session` from the maintained workspace so it cannot break root resolution.

**Tech Stack:** Python 3.12, `uv`, `hatchling`, `ruff`, `pytest`, `ty`, TOML packaging metadata

---

## File Map

**Create:**
- `uv.lock`
- `docs/superpowers/plans/2026-03-27-python-workspace-packaging.md`

**Modify:**
- `pyproject.toml`
- `passport-core/pyproject.toml`
- `passport-platform/pyproject.toml`
- `passport-api/pyproject.toml`
- `passport-telegram/pyproject.toml`
- `passport-benchmark/pyproject.toml`
- `passport-core/README.md`
- `passport-platform/README.md`
- `passport-api/README.md`
- `passport-telegram/README.md`
- `passport-benchmark/README.md`

**Do not modify in this migration:**
- `browser-session/pyproject.toml`
- `browser-session/src/...`
- maintained package source trees outside packaging/docs changes unless verification reveals a packaging-only fix is required

### Task 1: Audit Workspace Dependency Compatibility

**Files:**
- Modify: `pyproject.toml`
- Inspect: `passport-core/pyproject.toml`
- Inspect: `passport-platform/pyproject.toml`
- Inspect: `passport-api/pyproject.toml`
- Inspect: `passport-telegram/pyproject.toml`
- Inspect: `passport-benchmark/pyproject.toml`

- [ ] **Step 1: Record the maintained workspace members and exclude the experimental package**

```toml
[tool.uv.workspace]
members = [
  "passport-api",
  "passport-benchmark",
  "passport-core",
  "passport-platform",
  "passport-telegram",
]
```

- [ ] **Step 2: Inspect current dependency declarations for conflicts before editing manifests**

Run: `for f in passport-core/pyproject.toml passport-platform/pyproject.toml passport-api/pyproject.toml passport-telegram/pyproject.toml passport-benchmark/pyproject.toml; do echo "--- $f"; sed -n '1,220p' "$f"; done`
Expected: All maintained package dependencies are visible in one pass, including internal deps and tool duplication.

- [ ] **Step 3: Normalize shared tooling versions into one root dev group draft**

```toml
[dependency-groups]
dev = [
  "pytest>=8.3.2",
  "pytest-cov>=5.0.0",
  "ruff>=0.6.4",
  "ty>=0.0.24",
]
```

- [ ] **Step 4: Dry-run root resolution to catch incompatible version ranges early**

Run: `uv lock --dry-run`
Expected: Either a successful resolution summary or a concrete version conflict that must be fixed before continuing.

- [ ] **Step 5: Commit the audit checkpoint once the dependency picture is clear**

```bash
git add pyproject.toml
git commit -m "chore[codex]: define maintained workspace membership"
```

### Task 2: Make the Root `pyproject.toml` the Workspace Control Plane

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the root workspace manifest with shared tooling and internal sources**

```toml
[tool.uv]
package = false
default-groups = ["dev"]

[tool.uv.workspace]
members = [
  "passport-api",
  "passport-benchmark",
  "passport-core",
  "passport-platform",
  "passport-telegram",
]

[tool.uv.sources]
passport-core = { workspace = true }
passport-platform = { workspace = true }
passport-api = { workspace = true }
passport-telegram = { workspace = true }
passport-benchmark = { workspace = true }

[dependency-groups]
dev = [
  "pytest>=8.3.2",
  "pytest-cov>=5.0.0",
  "ruff>=0.6.4",
  "ty>=0.0.24",
]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "A", "SIM", "RET", "PTH"]

[tool.pytest.ini_options]
testpaths = [
  "passport-core/tests",
  "passport-platform/tests",
  "passport-api/tests",
  "passport-telegram/tests",
  "passport-benchmark/tests",
]
```

- [ ] **Step 2: Verify the root manifest is valid TOML before touching package manifests**

Run: `python3 - <<'PY'
from pathlib import Path
import tomllib
print(tomllib.loads(Path('pyproject.toml').read_text()))
PY`
Expected: Parsed TOML dictionary output with no syntax error.

- [ ] **Step 3: Confirm the workspace no longer includes `browser-session`**

Run: `rg -n "browser-session" pyproject.toml`
Expected: No `browser-session` workspace member remains.

- [ ] **Step 4: Confirm the root config exposes the shared tool settings**

Run: `sed -n '1,220p' pyproject.toml`
Expected: Root file contains `tool.uv.workspace`, `tool.uv.sources`, `dependency-groups`, `tool.ruff`, and `tool.pytest.ini_options`.

- [ ] **Step 5: Commit the workspace control-plane change**

```bash
git add pyproject.toml
git commit -m "build[codex]: centralize workspace tool configuration"
```

### Task 3: Thin the Maintained Package Manifests

**Files:**
- Modify: `passport-core/pyproject.toml`
- Modify: `passport-platform/pyproject.toml`
- Modify: `passport-api/pyproject.toml`
- Modify: `passport-telegram/pyproject.toml`
- Modify: `passport-benchmark/pyproject.toml`

- [ ] **Step 1: Reduce `passport-core/pyproject.toml` to distribution metadata and build target only**

```toml
[project]
name = "passport-core"
version = "0.2.0"
description = "Core passport processing services for Yemeni travel agencies"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "httpx>=0.27.0",
  "numpy>=1.26.4",
  "onnxruntime==1.19.2",
  "opencv-python-headless>=4.10.0.84",
  "pydantic-ai-slim[openai]>=0.0.39",
  "pydantic>=2.8.2",
  "pydantic-settings>=2.4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/passport_core"]
```

- [ ] **Step 2: Reduce `passport-platform/pyproject.toml` and keep only its internal dependency**

```toml
[project]
name = "passport-platform"
version = "0.1.0"
description = "Shared application services for passport adapters"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "passport-core",
  "pydantic-settings>=2.4.0",
]

[tool.uv.sources]
passport-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/passport_platform"]
```

- [ ] **Step 3: Reduce `passport-api/pyproject.toml` and keep its script entry point**

```toml
[project]
name = "passport-api"
version = "0.1.0"
description = "FastAPI adapter for passport-platform"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.118.0",
  "passport-platform",
  "pydantic-settings>=2.4.0",
  "python-multipart>=0.0.22",
  "uvicorn>=0.36.0",
]

[project.scripts]
passport-api = "passport_api.cli:main"

[tool.uv.sources]
passport-platform = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/passport_api"]
```

- [ ] **Step 4: Reduce `passport-telegram/pyproject.toml` and keep its script entry point**

```toml
[project]
name = "passport-telegram"
version = "0.1.0"
description = "Telegram bot adapter for passport-platform"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "passport-platform",
  "pydantic-settings>=2.4.0",
  "python-dotenv>=1.0.1",
  "python-telegram-bot[job-queue]>=21.6",
]

[project.scripts]
passport-telegram = "passport_telegram.cli:main"

[tool.uv.sources]
passport-platform = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/passport_telegram"]
```

- [ ] **Step 5: Reduce `passport-benchmark/pyproject.toml` and keep its CLI commands**

```toml
[project]
name = "passport-benchmark"
version = "0.2.0"
description = "Benchmark and evaluation suite for passport-core extraction"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "passport-core",
  "pydantic>=2.8.2",
]

[project.scripts]
benchmark-draft-unlabeled = "passport_benchmark.draft_unlabeled:main"
benchmark-organize = "passport_benchmark.organize:main"
benchmark-run = "passport_benchmark.runner:main"

[tool.uv.sources]
passport-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/passport_benchmark"]
```

- [ ] **Step 6: Verify no maintained package manifest still duplicates shared tooling config**

Run: `rg -n "\[tool\.ruff\]|\[tool\.pytest|\[dependency-groups\]|\[project\.optional-dependencies\]" passport-core/pyproject.toml passport-platform/pyproject.toml passport-api/pyproject.toml passport-telegram/pyproject.toml passport-benchmark/pyproject.toml`
Expected: No matches, or only matches intentionally left behind.

- [ ] **Step 7: Commit the package manifest reduction**

```bash
git add passport-core/pyproject.toml passport-platform/pyproject.toml passport-api/pyproject.toml passport-telegram/pyproject.toml passport-benchmark/pyproject.toml
git commit -m "build[codex]: thin maintained package manifests"
```

### Task 4: Update Documentation to Root-First Workflow

**Files:**
- Modify: `passport-core/README.md`
- Modify: `passport-platform/README.md`
- Modify: `passport-api/README.md`
- Modify: `passport-telegram/README.md`
- Modify: `passport-benchmark/README.md`

- [ ] **Step 1: Update `passport-core/README.md` setup and development commands to root-first usage**

```md
## Installation

```bash
uv sync --all-packages
cp passport-core/.env.example passport-core/.env
```

Set `PASSPORT_REQUESTY_API_KEY` in `passport-core/.env`.

## Development

```bash
uv run --package passport-core pytest passport-core/tests -q
uv run ruff check passport-core/src/
uv run ruff format passport-core/src/
```
```

- [ ] **Step 2: Update `passport-platform/README.md` setup and development commands**

```md
## Setup

```bash
uv sync --all-packages
cp passport-platform/.env.example passport-platform/.env
```

## Development

```bash
uv run --package passport-platform pytest passport-platform/tests -q
uv run ruff check passport-platform/src/
```
```

- [ ] **Step 3: Expand `passport-api/README.md` with root-first setup and run instructions**

```md
## Setup

```bash
uv sync --all-packages
cp passport-platform/.env.example passport-platform/.env
cp passport-core/.env.example passport-core/.env
cp passport-api/.env.example passport-api/.env
```

## Run

```bash
uv run passport-api
```

## Development

```bash
uv run --package passport-api pytest passport-api/tests -q
uv run ruff check passport-api/src/
```
```

- [ ] **Step 4: Update `passport-telegram/README.md` to root-first setup while keeping the package-specific env files**

```md
## Setup

```bash
uv sync --all-packages
cp passport-core/.env.example passport-core/.env
cp passport-platform/.env.example passport-platform/.env
cp passport-telegram/.env.example passport-telegram/.env
```

## Run

```bash
uv run passport-telegram
```

## Development

```bash
uv run --package passport-telegram pytest passport-telegram/tests -q
uv run ruff check passport-telegram/src/
```
```

- [ ] **Step 5: Update `passport-benchmark/README.md` to run from the root workspace**

```md
## Installation

```bash
uv sync --all-packages
```

## CLI

```bash
uv run benchmark-run cases/ --run-id <run-id>
uv run benchmark-run cases/ --extract --run-id <run-id>
uv run benchmark-organize <images-dir> cases/
uv run benchmark-draft-unlabeled cases/
```
```

- [ ] **Step 6: Verify the READMEs no longer teach package-local venv creation as the default path**

Run: `rg -n "uv venv|source \.venv/bin/activate|cd passport-" passport-core/README.md passport-platform/README.md passport-api/README.md passport-telegram/README.md passport-benchmark/README.md`
Expected: Either no matches, or only references that are explicitly called out as optional/package-local alternatives.

- [ ] **Step 7: Commit the documentation update**

```bash
git add passport-core/README.md passport-platform/README.md passport-api/README.md passport-telegram/README.md passport-benchmark/README.md
git commit -m "docs[codex]: document root-first workspace workflow"
```

### Task 5: Regenerate the Lockfile and Verify Root Workflows

**Files:**
- Create: `uv.lock`
- Verify: `pyproject.toml`
- Verify: `passport-core/pyproject.toml`
- Verify: `passport-platform/pyproject.toml`
- Verify: `passport-api/pyproject.toml`
- Verify: `passport-telegram/pyproject.toml`
- Verify: `passport-benchmark/pyproject.toml`

- [ ] **Step 1: Regenerate the workspace lockfile**

Run: `uv lock`
Expected: A new root `uv.lock` is generated without `browser-session` blocking resolution.

- [ ] **Step 2: Sync all maintained workspace packages into the root environment**

Run: `uv sync --all-packages`
Expected: Root `.venv` is created or updated successfully.

- [ ] **Step 3: Verify the lockfile is stable in CI mode**

Run: `uv sync --all-packages --locked`
Expected: Sync succeeds without modifying `uv.lock`.

- [ ] **Step 4: Verify shared linting from the root workspace**

Run: `uv run ruff check passport-core/src passport-platform/src passport-api/src passport-telegram/src passport-benchmark/src`
Expected: `All checks passed!`

- [ ] **Step 5: Verify representative tests from the root workspace**

Run: `uv run pytest passport-core/tests passport-platform/tests passport-api/tests passport-telegram/tests passport-benchmark/tests -q`
Expected: Passing tests, or targeted failures that reflect pre-existing issues rather than workspace packaging regressions.

- [ ] **Step 6: Verify runtime entry points resolve from the root workspace**

Run: `uv run passport-api --help`
Expected: The command resolves from the root workspace environment.

Run: `uv run passport-telegram --help`
Expected: The command resolves from the root workspace environment.

- [ ] **Step 7: Verify maintained distributions still build independently**

Run: `uv build --package passport-core && uv build --package passport-platform && uv build --package passport-api && uv build --package passport-telegram && uv build --package passport-benchmark`
Expected: Wheel and sdist artifacts build successfully for all maintained packages.

- [ ] **Step 8: Commit the lockfile and final packaging verification state**

```bash
git add uv.lock pyproject.toml passport-core/pyproject.toml passport-platform/pyproject.toml passport-api/pyproject.toml passport-telegram/pyproject.toml passport-benchmark/pyproject.toml passport-core/README.md passport-platform/README.md passport-api/README.md passport-telegram/README.md passport-benchmark/README.md
git commit -m "build[codex]: finalize root-managed uv workspace"
```

## Self-Review

### Spec coverage
- Root workspace control plane: covered in Task 2.
- `browser-session` exclusion: covered in Task 1 and Task 2.
- Shared tooling centralization: covered in Task 2 and Task 3.
- Thin per-package manifests: covered in Task 3.
- Root-first developer workflow: covered in Task 4.
- Root lockfile and `--locked` CI verification: covered in Task 5.
- Shared dependency conflict audit: covered in Task 1 and Task 5.

### Placeholder scan
- No `TODO`, `TBD`, or “implement later” markers remain.
- Each task contains exact file paths, exact commands, and concrete expected outcomes.

### Type and naming consistency
- Workspace members are consistently the maintained packages only.
- Internal dependency names consistently use `passport-core` and `passport-platform`.
- Root commands consistently use `uv` from the repository root.
