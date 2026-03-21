# User-Facing Text Guidelines

All user-facing strings are in Arabic. Developer/ops strings (RuntimeError, logs, error codes, JSON blobs) stay English.

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

Do not reference specific platform names in strings or variable names.
User-facing labels should describe the action, not the destination.
Internal identifiers should describe what the code does (e.g. `TEXT_FIELDS`, `score_normalized_prediction`).

## Where strings live

| Runtime | File |
|---|---|
| Python | `passport-platform/src/passport_platform/strings.py` |
| Extension | `passport-masar-extension/strings.js` |

All user-facing strings go through these files — no inline literals in routes, services, or UI code.
