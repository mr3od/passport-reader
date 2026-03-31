# AGENTS.md — passport-telegram

## Purpose

Agency-facing Telegram adapter only.

## Command scope

- Self-service agency commands only: `/start`, `/help`, `/account`, `/usage`, `/plan`, `/token`, `/masar`, `/extension`
- No admin/operator commands
- No cross-user lookups
- `/usage` is self-only and must not support argument-based lookups

## /extension command

- Delivers the Chrome extension ZIP to agencies via Telegram
- Fetches the ZIP at runtime from GitHub Releases using the `extension-latest` mutable tag
- Required env vars: `PASSPORT_GITHUB_RELEASE_READ_TOKEN`, `PASSPORT_GITHUB_REPO`
- `extension.py` uses a 5-minute TTL cache to avoid repeated GitHub API calls between requests
- Installation step screenshots (Arabic captions) are sent as a media group after the ZIP

## Strings

- Arabic bot-visible strings and formatting must stay in `src/passport_telegram/messages.py`
- Do not move Telegram command/help copy into `passport-platform`

## Runtime rules

- No chat allowlist
- Must depend on `passport-platform` only for business logic
- Must not import `passport-core`
- Telegram upload handling must remain bounded:
  - batch chunk size is controlled by `PASSPORT_TELEGRAM_MAX_IMAGES_PER_BATCH` and plan quota
  - in-flight limits are controlled by `PASSPORT_TELEGRAM_MAX_INFLIGHT_UPLOAD_BATCHES`
  - overload wait timeout is controlled by `PASSPORT_TELEGRAM_INFLIGHT_ACQUIRE_TIMEOUT_SECONDS`
