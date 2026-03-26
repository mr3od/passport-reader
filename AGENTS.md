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
| Python | `passport-platform/src/passport_platform/strings.py` |
| Extension | `passport-masar-extension/strings.js` |

All user-facing strings go through these files — no inline literals in routes, services, or UI code.

# Architecture Rules

These rules are intentionally small and strict. If a change conflicts with them, the change is probably wrong.

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

- `passport-api`, `passport-telegram`, and future admin tools must interact with business logic only through `passport-platform`.
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

## Extraction pipeline (passport-core 0.2.0+)

- The v2 extraction entry point is `passport_core.extraction.PassportExtractor`.
- `workflow.py`, `llm.py`, `models.py` in passport-core are deprecated v1 — do not extend them.
- Confidence is programmatic (image metadata + cross-validation warnings), never LLM self-reported.
- `passport-benchmark` is for scoring only — extraction logic lives in `passport-core`.

## Code quality

- Non-obvious functions must have a Python docstring.
- Deprecated modules must emit `DeprecationWarning` at import time and carry a `.. deprecated::` directive in their module docstring pointing to the replacement.

## Pre-commit checklist (all agents)

Before committing:
1. Run `uv run ruff check src/` and `uv run ruff format src/` — must pass.
2. Run `uv run ty check src` — must pass.
3. Verify non-obvious functions have Python docstrings.
4. If changes are large or structural, update the package's `AGENTS.md` and `README.md`.
5. Bump the version in `pyproject.toml` and `__version__` if the public API changed.
6. After commit, append to `docs/HISTORY.md` what was done and which agent authored the commit.
7. Include the agent name in the commit message (e.g. `[claude]`, `[codex]`, `[kiro]`, `[antigravity]`).

## Simplicity rule

- Before building complex infrastructure, check whether a proven package already solves the problem well enough.
- Prefer existing packages for cross-cutting concerns such as queueing, monitoring, analytics, and architecture enforcement.
- Do not add a dependency if the problem is small, domain-specific, or already simple in the current codebase.
- If building in-house anyway, the reason must be clear: boundary control, simplicity, cost, or missing fit.
