# Telegram Broadcast Design

## Goal

Allow an admin to broadcast either:
- a text message
- a photo with caption

from the admin Telegram bot to all active agency users as a notification.

## Scope

In scope:
- add an admin-only `/broadcast` command
- support `/broadcast <text>` for text-only broadcasts
- support replying with `/broadcast` to an admin photo message to broadcast that photo and its caption
- deliver broadcasts only to active Telegram users
- use the agency bot for final delivery so Telegram allows the messages
- persist enough broadcast state to survive process restarts and track completion

Out of scope:
- targeting by plan, segment, or explicit user ids
- scheduled broadcasts
- message editing or cancellation
- video, document, or album broadcasts
- a full operator campaign dashboard

## Current State

Today:
- the admin bot can run privileged operator commands through `passport-platform`
- the agency bot is the bot that agency users have already started and can receive messages from
- the platform can look up users, but it has no concept of a queued broadcast job

Important Telegram constraint:
- one bot cannot reliably reuse another bot's `file_id`
- one bot cannot message users who have only started a different bot

That means the admin bot cannot directly fan out messages to agency users, and the agency bot cannot safely send an admin photo by reusing the admin bot's Telegram media reference.

## Decision

Use a platform-backed broadcast queue with agency-bot delivery.

Flow:
1. admin issues `/broadcast <text>` or replies `/broadcast` to a photo
2. admin bot validates the command and creates a broadcast record in `passport-platform`
3. for photo broadcasts, admin bot downloads the photo bytes and stores them as a platform artifact
4. agency bot runs a lightweight background poller
5. agency bot claims pending broadcasts, loads all active Telegram users, and sends the content through its own bot token
6. platform records progress and marks the broadcast complete when fanout finishes

This is the smallest design that actually works with Telegram's rules.

## Command UX

### Text broadcast

Admin command:

```text
/broadcast System maintenance tonight at 11pm.
```

Behavior:
- create a text broadcast
- reply immediately to the admin with a queued confirmation

### Photo broadcast

Admin flow:
- admin sends a photo with optional caption
- admin replies to that photo with `/broadcast`

Behavior:
- photo becomes the broadcast media
- the original photo caption becomes the broadcast caption
- reply immediately to the admin with a queued confirmation

### Invalid usage

If the command has neither inline text nor a replied-to photo, the admin bot should return a short usage message.

If the admin replies to a non-photo message with `/broadcast`, the bot should reject it with a short usage error.

## Data Model

Add a new broadcast table owned by `passport-platform`.

Recommended fields:
- `id`
- `created_by_external_user_id`
- `content_type` with values `text` or `photo`
- `text_body`
- `caption`
- `artifact_path`
- `status` with values `pending`, `processing`, `completed`, `failed`
- `total_targets`
- `sent_count`
- `failed_count`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`

Notes:
- `artifact_path` is only used for photo broadcasts
- text broadcasts keep `artifact_path` null
- completion counters live on the broadcast row to avoid inventing a second per-user delivery table in v1

This is intentionally simple. We need one durable queue, not a warehouse.

## Platform Design

### User selection

Add a platform path that returns all active users for one provider:
- `list_active_users_by_provider(ExternalProvider.TELEGRAM)`

This filtering belongs in `passport-platform`, not in either adapter.

### Broadcast service

Add a `BroadcastService` in `passport-platform` that owns:
- creating text broadcasts
- creating photo broadcasts
- claiming the next pending broadcast
- marking a broadcast as started
- updating sent and failed counters
- marking a broadcast as completed or failed

The admin bot and agency bot should both talk only to this service.

### Artifact storage

Store admin-uploaded broadcast photos through platform artifact storage rather than raw database blobs.

Reason:
- it matches the platform rule that filesystem state belongs in `passport-platform`
- it avoids stuffing image bytes into SQLite
- it gives the agency bot a stable local file path to re-upload

## Adapter Design

### Admin bot

Add `/broadcast` to the admin bot.

Responsibilities:
- verify the caller is an admin
- parse text-broadcast vs reply-to-photo-broadcast usage
- for photo broadcasts, download the best available photo bytes from Telegram
- hand the payload to `BroadcastService`
- reply with a queued confirmation such as:
  - text: queued successfully
  - photo: queued successfully

The admin bot should not attempt delivery itself.

### Agency bot

Add a background broadcast worker to the agency bot application lifecycle.

Responsibilities:
- poll for one pending broadcast at a time
- claim it so only one worker processes it
- load all active Telegram users
- send text with `send_message` or photo with `send_photo`
- continue on per-user send failures
- update counters as delivery progresses
- mark the broadcast complete when done

The worker should sleep briefly when no broadcast is pending.

## Delivery Behavior

Best effort fanout is the right v1 behavior.

Rules:
- one failed recipient must not abort the whole broadcast
- blocked users are excluded before sending by targeting only active users
- if Telegram rejects a specific chat, count it as failed and move on
- if the worker crashes before completion, the broadcast remains visible in durable storage and can be retried safely after restart

For v1, retry means reprocessing the whole broadcast only if it never reached `completed`.
We do not need per-user deduplication yet.

## Admin Feedback

Because delivery happens asynchronously through the agency bot, the admin bot should not claim final `sent` and `failed` totals at queue time.

Immediate admin response should be:
- queued confirmation only

Completion details should be stored in the broadcast row for later inspection and logs.

If we want operator status commands later, that can be a separate small feature.

## Error Handling

Admin bot:
- reject invalid command forms with a short usage message
- reject reply-to-non-photo broadcasts
- fail cleanly if photo download fails

Agency bot:
- catch Telegram send exceptions per recipient
- log send failures with the broadcast id and external user id
- mark the whole broadcast `failed` only for systemic errors such as unreadable artifact or unrecoverable queue-state problems

Platform:
- claiming a broadcast should be atomic so two workers do not process the same job
- photo artifact creation should happen before the broadcast row is finalized

## Testing Plan

### Platform tests

Add tests for:
- creating a text broadcast
- creating a photo broadcast
- listing active Telegram users only
- claiming the next pending broadcast exactly once
- updating counters and final status

### Admin bot tests

Add tests for:
- `/broadcast <text>` queues a text broadcast
- `/broadcast` replying to a photo queues a photo broadcast
- invalid `/broadcast` usage returns help text
- non-admin users are rejected

### Agency bot tests

Add tests for:
- worker sends text broadcasts to active users
- worker sends photo broadcasts by re-uploading stored bytes
- one recipient failure does not stop the rest
- completed broadcasts are marked with final counts

## Files Expected To Change

Platform:
- `passport-platform/src/passport_platform/db.py`
- `passport-platform/migrations/0002_indexes.sql` or a new migration file
- `passport-platform/src/passport_platform/factory.py`
- `passport-platform/src/passport_platform/models/`
- `passport-platform/src/passport_platform/repositories/`
- `passport-platform/src/passport_platform/services/`
- `passport-platform/tests/`

Admin bot:
- `passport-admin-bot/src/passport_admin_bot/bot.py`
- `passport-admin-bot/src/passport_admin_bot/messages.py`
- `passport-admin-bot/tests/test_bot.py`
- `passport-admin-bot/README.md`

Agency bot:
- `passport-telegram/src/passport_telegram/bot.py`
- `passport-telegram/tests/test_bot.py`

## Risks

### Duplicate sends after crash

Without per-user delivery rows, a crash during fanout can cause some users to receive the same broadcast twice if the whole job is retried. That is acceptable for v1 because the feature goal is simple operator notifications, not exactly-once messaging.

### Long fanout time

A large user base means one broadcast may take time to finish. That is acceptable for v1 because broadcast volume is expected to be low and the worker is simple.

### Partial implementation risk

If we add the admin command without durable queueing and agency-bot delivery, the feature will look complete but fail under real Telegram constraints. All three layers must move together.

## Verification Plan

Minimum verification after implementation:
- `uv run pytest passport-platform/tests -q`
- `uv run pytest passport-admin-bot/tests -q`
- `uv run pytest passport-telegram/tests -q`
- `uv run ruff check passport-platform/src passport-platform/tests passport-admin-bot/src passport-admin-bot/tests passport-telegram/src passport-telegram/tests`
- `uv run ruff format passport-platform/src passport-platform/tests passport-admin-bot/src passport-admin-bot/tests passport-telegram/src passport-telegram/tests`
- `uv run ty check passport-platform passport-admin-bot passport-telegram`

If imports or package boundaries change materially, also run:
- `uv run lint-imports`
