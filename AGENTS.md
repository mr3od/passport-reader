# User-Facing Text Guidelines

All user-facing strings are in Arabic. Developer/ops strings (RuntimeError, logs, error codes, JSON blobs) stay English.

This applies to product/runtime text shown to agency users inside the system. It does not apply to developer collaboration in this workspace: agent replies, code review comments, commit messages, shell guidance, and implementation discussion with repository developers stay English unless the developer explicitly asks for Arabic.

## Tone

Short, direct, non-technical. Agencies are not developers.

## Vocabulary

| Use | Avoid |
|---|---|
| جواز / جوازات | سجل |
| رفع | إرسال |
| انتهت الجلسة | انتهت صلاحية الجلسة |
| تحديث | مزامنة |

Avoid: رمز التحقق، رأس التفويض، طلب API

## Platform names

User-facing labels must describe the action, not the destination. Do not reference specific platform names in strings.

## Identifier naming

Internal identifiers must describe what the code does, not which platform or product it relates to (e.g. `TEXT_FIELDS`, `score_normalized_prediction`).

## Where strings live

| Runtime | File |
|---|---|
| Python runtime/API | `passport-platform/src/passport_platform/strings.py` |
| Agency Telegram bot | `passport-telegram/src/passport_telegram/messages.py` |
| Admin Telegram bot | inside `passport-admin-bot/src/passport_admin_bot/` |
| Extension | `passport-masar-extension/strings.js` |

All user-facing strings go through these files — no inline literals in routes, services, or UI code.

Telegram adapter exception:
- agency bot-visible Arabic strings and formatting stay in `passport-telegram/src/passport_telegram/messages.py`
- admin bot-visible strings and formatting stay inside `passport-admin-bot`
- `passport-platform/src/passport_platform/strings.py` is for platform/runtime Python strings, not Telegram command/help copy

# Architecture Rules

These rules are intentionally small and strict. If a change conflicts with them, the change is probably wrong.

## Workspace Workflow

- The maintained Python workspace is defined by the root `pyproject.toml`.
- Use `uv` from the repository root for installs, commands, and builds.
- Use the root `.env` for local development and the root `.env.production` contract for production.
- Do not reintroduce package-local `.env` workflows for `passport-core`, `passport-platform`, `passport-api`, `passport-telegram`, or `passport-admin-bot`.
- Shared tooling is configured at the root workspace level:
  - `import-linter`
  - `ruff`
  - `pytest`
  - `ty`
- Production deployment is Kubernetes-first:
  - versioned manifests under `k8s/`
  - MicroK8s in production
  - CI applies manifests and rollout checks from the root workspace

## Package boundaries

### `passport-core`

- Must not depend on any other repo package.
- Must not access the database.
- Must not write application state to the filesystem.
- May only read local files for models, templates, and benchmark/test inputs.

### `passport-platform`

- Is the only package allowed to import `passport-core`.
- Is the only package allowed to access the database and application filesystem state.
- Owns business logic, persistence, quotas, users, records, and processing orchestration.

### Adapters

- `passport-api`, `passport-telegram`, `passport-admin-bot`, and future admin tools must interact with business logic only through `passport-platform`.
- Adapters must not import `passport-core`.
- Adapters must not implement business rules that belong in `passport-platform`.

### Extension

- `passport-masar-extension` may only interact with backend state through HTTP requests to `passport-api`.
- It must not access database, platform, or core code directly.

### Queueing

- If background processing is introduced, `passport-platform` owns enqueueing, dequeueing, retries, and job state.
- `passport-core` only processes in-memory payloads passed to it.

## Schema changes

Adding a column requires all of the following to be updated together — a partial change is a broken change:

1. `_upgrade_schema()` in `passport-platform/src/passport_platform/db.py` — `ALTER TABLE` so existing databases migrate on startup
2. The reference `.sql` file in `passport-platform/migrations/`
3. The `ProcessingResult` dataclass in `models/upload.py`
4. The `UserRecord` schema in `schemas/results.py`
5. The SELECT queries in `repositories/records.py`
6. The `RecordResponse` schema and route logic in `passport-api`

## Extraction pipeline (passport-core 0.3.0+)

- The v2 extraction entry point is `passport_core.extraction.PassportExtractor`.
- `workflow.py`, `llm.py`, and the old v1 extraction models have been removed from `passport-core`.
- Confidence is programmatic (image metadata + cross-validation warnings), never LLM self-reported.
- `passport-benchmark` is for scoring only — extraction logic lives in `passport-core`.

## Code quality

- Non-obvious functions must have a Python docstring.
- Deprecated modules must emit `DeprecationWarning` at import time and carry a `.. deprecated::` directive in their module docstring pointing to the replacement.

## Pre-commit checklist (all agents)

Before committing:
1. Run `uv run ruff check ...` and `uv run ruff format ...` for the touched Python packages from the repository root — must pass.
2. Run `uv run lint-imports` from the repository root when package boundaries or imports may be affected — must pass.
3. Run `uv run ty check ...` for the touched Python packages from the repository root — must pass.
4. Run `uv run pytest ...` for the affected package tests from the repository root — must pass.
5. Verify non-obvious functions have Python docstrings.
6. If changes are large or structural, update the package's `AGENTS.md` and `README.md`.
7. Bump the version in `pyproject.toml` and `__version__` if the public API changed.
8. After commit, append to `docs/HISTORY.md` what was done and which agent authored the commit.
9. Include the agent name in the commit message (e.g. `[claude]`, `[codex]`, `[kiro]`, `[antigravity]`).

## Simplicity rule

- Before building complex infrastructure, check whether a proven package already solves the problem well enough.
- Prefer existing packages for cross-cutting concerns such as queueing, monitoring, analytics, and architecture enforcement.
- Do not add a dependency if the problem is small, domain-specific, or already simple in the current codebase.
- If building in-house anyway, the reason must be clear: boundary control, simplicity, cost, or missing fit.
