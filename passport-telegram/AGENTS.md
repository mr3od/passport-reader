# AGENTS.md — passport-telegram

## Purpose

Agency-facing Telegram adapter only.

## Command scope

- Self-service agency commands only: `/start`, `/help`, `/account`, `/usage`, `/plan`, `/token`, `/masar`
- No admin/operator commands
- No cross-user lookups
- `/usage` is self-only and must not support argument-based lookups

## Strings

- Arabic bot-visible strings and formatting must stay in `src/passport_telegram/messages.py`
- Do not move Telegram command/help copy into `passport-platform`

## Runtime rules

- No chat allowlist
- Must depend on `passport-platform` only for business logic
- Must not import `passport-core`
