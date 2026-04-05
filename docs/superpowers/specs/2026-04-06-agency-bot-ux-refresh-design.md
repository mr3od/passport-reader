# Agency Bot UX Refresh Design

## Goal

Make the agency Telegram bot simpler, friendlier, and more effective by:
- removing redundant commands
- rewriting user-facing Arabic copy in a warm, respectful style that fits Yemeni users
- making the extension the clearly recommended path for full system usage

## Scope

In scope:
- simplify the agency bot command set
- remove overlapping account/status commands
- introduce one primary status command
- rewrite welcome/help/account/error messages
- make the extension recommendation obvious in the right places
- update tests and README to match the new UX contract

Out of scope:
- changing the OCR or processing pipeline
- changing quotas or plan rules
- adding buttons, menus, or inline keyboards
- changing admin bot behavior
- changing extension UX itself

## Current State

Today the agency bot exposes:
- `/start`
- `/help`
- `/account`
- `/usage`
- `/plan`
- `/token`
- `/masar`
- `/extension`

Problems:
- `/account`, `/usage`, and `/plan` overlap too much
- `/start` and `/help` read more like documentation than a guided tool
- the copy is serviceable but still a bit stiff
- the extension exists, but the bot does not clearly position it as the recommended full workflow

## Decision

Use a hard simplification approach.

Keep only the commands that map directly to a real user job:
- `/start`
- `/help`
- `/me`
- `/token`
- `/masar`
- `/extension`

Remove:
- `/account`
- `/usage`
- `/plan`

This is the right trade-off. Agency users should not have to guess which of three similar commands gives the “real” account view.

Use a hard cut, not aliases. The cleanup should be obvious and final.

## Command Design

### `/start`

Purpose:
- welcome the user
- tell them the next action immediately
- explain that the bot can process passport images directly
- explain that the extension is the recommended path for the full workflow

Requirements:
- short
- action-first
- no long command dump
- include a direct instruction to send a passport image now
- mention `/extension` as the recommended setup for full use and Masar-related flow

### `/help`

Purpose:
- explain how to use the service in plain language
- list only the commands that remain

Requirements:
- short practical steps
- supported file types
- one short line explaining that the extension unlocks the full workflow

### `/me`

Purpose:
- replace `/account`, `/usage`, and `/plan`

Contents:
- user label
- Telegram id
- plan
- account status
- uploads this month
- successful processes
- failed processes
- remaining uploads
- remaining successful processes

Optional guidance:
- include one short extension hint for active users, such as using the extension for the full workflow and Masar follow-up

### `/token`

Purpose:
- stay focused on extension login

Requirement:
- the copy should clearly tell the user this token is for the extension and expires soon

### `/masar`

Purpose:
- keep it as the follow-up command for pending/failed Masar cases

Requirement:
- wording should assume non-technical users
- when failures exist, the next action should point users toward the extension rather than vaguely telling them to retry

### `/extension`

Purpose:
- become the explicit “recommended setup” command

Requirement:
- its surrounding copy should frame the extension as the full-use path, not just an optional add-on

## Tone Design

The Arabic tone should be:
- warm
- respectful
- clear
- lightly local in feel without heavy slang

It should not be:
- robotic
- overly formal
- preachy
- full of dense instructions

This should feel like a capable service speaking to agencies in a familiar, trustworthy way.

## Messaging Rules

### Welcome and help

Lead with:
- what the user can do now
- what the best next action is

Do not lead with:
- command catalogs
- system internals
- long explanatory paragraphs

### Success messages

Processing success should:
- open with a warm, concise success line
- keep the structured data output because it is useful
- avoid sounding like a machine report before showing the useful fields

### Failure messages

Failure copy should:
- say what likely happened in plain words
- tell the user what to try next
- avoid blame

### Busy/quota/block messages

These should remain direct and respectful.

They should tell the user:
- what happened
- whether they can retry later
- when support or extension guidance is relevant

## Extension Positioning

The bot should make this clear within the first interaction:
- direct image processing in Telegram is supported
- the extension is the recommended path for full use
- Masar-related follow-up is best handled through the extension

Where to say this:
- `/start`
- `/help`
- `/me`
- `/masar`
- `/extension`

Where not to repeat it constantly:
- every upload success
- every upload failure
- generic system errors

The goal is guidance, not nagging.

## Adapter Design

`passport-telegram/src/passport_telegram/bot.py` should:
- register `/me`
- remove `/account`
- remove `/usage`
- remove `/plan`
- route `/me` to the same reporting flow that currently powers the account/usage summary

`passport-telegram/src/passport_telegram/messages.py` should:
- own all rewritten Arabic strings
- keep strings centralized
- avoid inline literals elsewhere

## Testing Plan

Update tests to prove:
- `/me` returns the consolidated user account summary
- `/usage` with args no longer represents the supported public flow
- removed command handlers are no longer registered
- revised welcome/help strings mention the extension as the recommended full workflow
- key Arabic messages still remain short and action-oriented

## Files Expected To Change

- `passport-telegram/src/passport_telegram/bot.py`
- `passport-telegram/src/passport_telegram/messages.py`
- `passport-telegram/tests/test_bot.py`
- `passport-telegram/tests/test_messages.py`
- `passport-telegram/README.md`

## Risks

### Over-localizing the tone

If the copy leans too hard into slang, it may feel gimmicky or regionally narrow. The design should stay respectful and broadly understandable first.

### Too much extension promotion

If every message pushes the extension, users will tune it out. The recommendation should appear in the right moments, not everywhere.

### Command migration confusion

Users familiar with `/account` or `/plan` may notice the command change. The design accepts that short-term adjustment in exchange for a cleaner permanent command surface.

## Verification Plan

Minimum verification after implementation:
- `uv run pytest passport-telegram/tests/test_bot.py -q`
- `uv run pytest passport-telegram/tests/test_messages.py -q`
- `uv run ruff check passport-telegram/src passport-telegram/tests`
- `uv run ruff format passport-telegram/src passport-telegram/tests`
- `uv run ty check passport-telegram`
