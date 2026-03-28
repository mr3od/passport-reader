# AGENTS.md — passport-admin-bot

## Purpose

Admin/operator Telegram adapter only.

## Command scope

- Admin-only commands: `/start`, `/help`, `/admin`, `/stats`, `/recent`, `/usage`, `/setplan`, `/block`, `/unblock`
- Cross-user lookups and operator actions live here, not in `passport-telegram`

## Strings

- Bot-visible strings and formatting are English
- Keep them inside `src/passport_admin_bot/`

## Boundaries

- Must interact with business logic only through `passport-platform`
- Must not import `passport-core`
- Must not implement domain rules that belong in `passport-platform`
