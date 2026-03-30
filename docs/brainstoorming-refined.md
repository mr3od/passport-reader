

I'm using the task-architect skill to generate your execution list.

---

# Pre-Architecture: Correction Applied

## What Changed

### `needs_review` comes from OUR system, not from Nusuk

**Wrong assumption (previous plan):** Nusuk returns `needs_review` after submission.

**Correct model:**
- `needs_review` is set by **our API** during passport processing (OCR/validation stage), before any Nusuk submission
- It means: "we extracted the data but something looks off — the user should double-check before or after submission"
- The extension **submits these passports normally** to Nusuk — `needs_review` does NOT block submission
- After submission, both `submitted` and `submitted + needs_review` passports appear in the Submitted section
- `needs_review` passports get an amber badge so the user knows to go review on Nusuk

### Updated data flow

```
Our API processes passport:
  → upload_status = 'processed', needs_review = true   ← our flag
  → upload_status = 'processed', needs_review = false   ← clean

Extension submits to Nusuk:
  → masar_status = 'submitted'   (Nusuk accepted)
  → masar_status = 'failed'     (Nusuk rejected)
  → Nusuk NEVER returns 'needs_review'

Submitted section shows:
  → Green badge: submitted + !needs_review  → clean
  → Amber badge: submitted + needs_review   → user should review on Nusuk
```

### What this changes in the plan

| Component | Change |
|---|---|
| `status.js` | `needs_review` is a boolean flag on the record, NOT a `masar_status` value |
| `queue-filter.js` | Queue section includes `needs_review` records (they're submittable). Submitted section uses `needs_review` flag for badge color |
| Background submission loop | Submits `needs_review` records the same as any other — no special handling |
| Popup cards | Queue cards for `needs_review` passports show amber indicator but still have submit button. Submitted cards with `needs_review = true` show amber badge + click-to-redirect |
| Notifications | `NEEDS_REVIEW` notification removed — not triggered by Nusuk response |

### Updated status/badge matrix

**Queue section (ready to submit to Nusuk):**

| Record state | Badge | Action |
|---|---|---|
| `processed` + `!needs_review` | Blue "جاهز" | Submit button |
| `processed` + `needs_review` | Amber "يحتاج مراجعة" | Submit button (still submittable) |

**Submitted section (already in Nusuk):**

| Record state | Badge | Click action |
|---|---|---|
| `submitted` + `!needs_review` | Green "تم الرفع" | Opens Nusuk detail page |
| `submitted` + `needs_review` | Amber "تم الرفع - يحتاج مراجعة" | Opens Nusuk detail page |

**Other sections unchanged:**

| Section | Records |
|---|---|
| Pending | `upload_status = 'pending'` |
| Failed | `upload_status = 'failed'` OR `masar_status = 'failed'` |

---

# Structural Mapping

## New Files

| Path | Purpose |
|---|---|
| `passport-masar-extension/src/strings.js` | Centralized Arabic UI strings |
| `passport-masar-extension/src/context-change.js` | Context change detection, debounce, buffering, submission state machine |
| `passport-masar-extension/src/badge.js` | Badge priority manager |
| `passport-masar-extension/src/notifications.js` | Notification layer with deduplication |
| `passport-masar-extension/src/status.js` | Status label + color mapping (uses `needs_review` as boolean flag) |
| `passport-masar-extension/src/contract-select.js` | Contract auto-select |
| `passport-masar-extension/src/mutamer-url.js` | Nusuk mutamer detail URL builder |
| `passport-masar-extension/src/queue-filter.js` | Splits records into queue/pending/submitted/failed |
| `passport-masar-extension/tests/*.test.js` | All corresponding test files |
| `passport-telegram/tests/test_messages_text.py` | Telegram text tests |

## Modified Files

| Path | Change |
|---|---|
| `passport-masar-extension/src/background.js` | Debounced context buffering; badge; notifications on batch complete; submission state machine; submits `needs_review` records normally |
| `passport-masar-extension/src/popup.js` | Four-section rendering; passport images; badges; click-to-redirect; context-change banner |
| `passport-masar-extension/src/popup.html` | DOM structure for four sections |
| `passport-masar-extension/manifest.json` | Add `notifications` permission |
| `passport-telegram/bot/messages.py` | Rewrite texts per consensus |

---

# Task List

---

## Task 1: Centralized Arabic Strings

- **Files:** `passport-masar-extension/src/strings.js`, `passport-masar-extension/tests/strings.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/strings.test.js
import { STRINGS } from '../src/strings.js';

describe('STRINGS', () => {
  test('context change strings', () => {
    expect(STRINGS.CTX_CHANGE_PROMPT).toBe("تم تغيير الحساب أو العقد. هل تريد التبديل إليه؟");
    expect(STRINGS.CTX_CHANGE_YES).toBe("نعم، بدّل");
    expect(STRINGS.CTX_CHANGE_LATER).toBe("لاحقًا");
    expect(STRINGS.CTX_CHANGE_QUEUED).toBe("سيتم التبديل بعد اكتمال الرفع الحالي.");
    expect(STRINGS.CTX_CHANGED_ENTITY).toBe("تم تغيير الحساب. اختر المجموعة مرة أخرى للمتابعة.");
    expect(STRINGS.CTX_CHANGED_CONTRACT).toBe("تم تغيير العقد. اختر المجموعة المناسبة للمتابعة.");
    expect(STRINGS.CTX_CHANGED_GENERIC).toBe("تم تغيير الحساب أو العقد. اختر المجموعة مرة أخرى للمتابعة.");
  });

  test('status labels', () => {
    expect(STRINGS.STATUS_READY).toBe("جاهز");
    expect(STRINGS.STATUS_NEEDS_REVIEW).toBe("يحتاج مراجعة");
    expect(STRINGS.STATUS_PROCESSING).toBe("قيد المعالجة");
    expect(STRINGS.STATUS_SUBMITTED).toBe("تم الرفع");
    expect(STRINGS.STATUS_SUBMITTED_NEEDS_REVIEW).toBe("تم الرفع - يحتاج مراجعة");
    expect(STRINGS.STATUS_FAILED).toBe("فشل");
    expect(STRINGS.STATUS_SESSION_EXPIRED).toBe("انتهت الجلسة");
  });

  test('section headers', () => {
    expect(STRINGS.SECTION_QUEUE).toBe("قائمة الرفع");
    expect(STRINGS.SECTION_PENDING).toBe("قيد المعالجة");
    expect(STRINGS.SECTION_SUBMITTED).toBe("تم الرفع");
    expect(STRINGS.SECTION_FAILED).toBe("فشل");
  });

  test('action labels', () => {
    expect(STRINGS.ACTION_SUBMIT).toBe("رفع");
    expect(STRINGS.ACTION_SUBMIT_ALL).toBe("رفع الكل");
    expect(STRINGS.ACTION_RETRY).toBe("إعادة المحاولة");
  });

  test('detail and help', () => {
    expect(STRINGS.VIEW_DETAILS).toBe("عرض التفاصيل");
    expect(STRINGS.DETAILS_UNAVAILABLE).toBe("تفاصيل غير متوفرة");
    expect(STRINGS.HELP_LINK_LABEL).toBe("مساعدة");
    expect(STRINGS.CONTRACT_EXPIRED).toBeDefined();
  });

  test('notification strings', () => {
    expect(STRINGS.NOTIF_BATCH_COMPLETE).toBeDefined();
    expect(STRINGS.NOTIF_SESSION_EXPIRED).toBeDefined();
  });

  test('all non-empty strings', () => {
    for (const [, v] of Object.entries(STRINGS)) {
      expect(typeof v).toBe('string');
      expect(v.length).toBeGreaterThan(0);
    }
  });

  test('frozen', () => {
    expect(Object.isFrozen(STRINGS)).toBe(true);
  });
});
```

  - Expected Failure: `Cannot find module '../src/strings.js'`

- [ ] **Step 2: Logic Specification**
  - **Signature:** `export const STRINGS = Object.freeze({ ... })`
  - Frozen object with all keys above. Note `STATUS_SUBMITTED_NEEDS_REVIEW` is new — used for submitted passports that also have `needs_review = true`. No `NOTIF_NEEDS_REVIEW` (removed — our system flags it, no notification needed).

- [ ] **Step 3: Verification**
  - `npx jest tests/strings.test.js`

- [ ] **Step 4: Commit**
  - `feat: add centralized Arabic strings module`

---

## Task 2: Status Label and Color Mapping

- **Files:** `passport-masar-extension/src/status.js`, `passport-masar-extension/tests/status.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/status.test.js
import { getStatusLabel, getStatusColor } from '../src/status.js';
import { STRINGS } from '../src/strings.js';

describe('getStatusLabel', () => {
  // Queue states (before Nusuk submission)
  test('ready: processed, no needs_review', () => {
    expect(getStatusLabel({ upload_status: 'processed', masar_status: null, needs_review: false }))
      .toBe(STRINGS.STATUS_READY);
  });

  test('needs review in queue: processed, needs_review true, not yet submitted', () => {
    expect(getStatusLabel({ upload_status: 'processed', masar_status: null, needs_review: true }))
      .toBe(STRINGS.STATUS_NEEDS_REVIEW);
  });

  test('processing: pending', () => {
    expect(getStatusLabel({ upload_status: 'pending', masar_status: null, needs_review: false }))
      .toBe(STRINGS.STATUS_PROCESSING);
  });

  // Submitted states
  test('submitted clean', () => {
    expect(getStatusLabel({ upload_status: 'processed', masar_status: 'submitted', needs_review: false }))
      .toBe(STRINGS.STATUS_SUBMITTED);
  });

  test('submitted with needs_review', () => {
    expect(getStatusLabel({ upload_status: 'processed', masar_status: 'submitted', needs_review: true }))
      .toBe(STRINGS.STATUS_SUBMITTED_NEEDS_REVIEW);
  });

  // Failed states
  test('masar failed', () => {
    expect(getStatusLabel({ upload_status: 'processed', masar_status: 'failed', needs_review: false }))
      .toBe(STRINGS.STATUS_FAILED);
  });

  test('upload failed', () => {
    expect(getStatusLabel({ upload_status: 'failed', masar_status: null, needs_review: false }))
      .toBe(STRINGS.STATUS_FAILED);
  });

  test('failed overrides needs_review', () => {
    expect(getStatusLabel({ upload_status: 'failed', masar_status: null, needs_review: true }))
      .toBe(STRINGS.STATUS_FAILED);
  });

  test('defaults to processing for unknown', () => {
    expect(getStatusLabel({ upload_status: 'xyz' })).toBe(STRINGS.STATUS_PROCESSING);
  });

  test('handles missing needs_review (defaults false)', () => {
    expect(getStatusLabel({ upload_status: 'processed', masar_status: null }))
      .toBe(STRINGS.STATUS_READY);
  });

  test('handles missing needs_review on submitted', () => {
    expect(getStatusLabel({ upload_status: 'processed', masar_status: 'submitted' }))
      .toBe(STRINGS.STATUS_SUBMITTED);
  });
});

describe('getStatusColor', () => {
  test('green for submitted clean', () => {
    expect(getStatusColor({ upload_status: 'processed', masar_status: 'submitted', needs_review: false })).toBe('green');
  });

  test('amber for submitted + needs_review', () => {
    expect(getStatusColor({ upload_status: 'processed', masar_status: 'submitted', needs_review: true })).toBe('amber');
  });

  test('amber for queue + needs_review', () => {
    expect(getStatusColor({ upload_status: 'processed', masar_status: null, needs_review: true })).toBe('amber');
  });

  test('blue for ready', () => {
    expect(getStatusColor({ upload_status: 'processed', masar_status: null, needs_review: false })).toBe('blue');
  });

  test('red for failed', () => {
    expect(getStatusColor({ upload_status: 'failed', masar_status: null, needs_review: false })).toBe('red');
  });

  test('gray for pending', () => {
    expect(getStatusColor({ upload_status: 'pending' })).toBe('gray');
  });
});
```

  - Expected Failure: `Cannot find module '../src/status.js'`

- [ ] **Step 2: Logic Specification**
  - **Signatures:**
    - `export function getStatusLabel({ upload_status, masar_status, needs_review }): string`
    - `export function getStatusColor({ upload_status, masar_status, needs_review }): string`
  - `needs_review` is a **boolean flag** on the record, defaulting to `false` if absent.
  - `getStatusLabel` priority: (1) either status `'failed'` → `STATUS_FAILED`; (2) `masar_status === 'submitted'` AND `needs_review` → `STATUS_SUBMITTED_NEEDS_REVIEW`; (3) `masar_status === 'submitted'` AND `!needs_review` → `STATUS_SUBMITTED`; (4) `upload_status === 'processed'` AND no `masar_status` AND `needs_review` → `STATUS_NEEDS_REVIEW`; (5) `upload_status === 'processed'` AND no `masar_status` AND `!needs_review` → `STATUS_READY`; (6) `upload_status === 'pending'` → `STATUS_PROCESSING`; (7) default → `STATUS_PROCESSING`.
  - `getStatusColor`: failed→`'red'`, submitted+needs_review→`'amber'`, submitted→`'green'`, queue+needs_review→`'amber'`, ready→`'blue'`, pending→`'gray'`.

- [ ] **Step 3: Verification**
  - `npx jest tests/status.test.js`

- [ ] **Step 4: Commit**
  - `feat: add status label mapping with needs_review as boolean flag`

---

## Task 3: Queue Filter — Four Sections

- **Files:** `passport-masar-extension/src/queue-filter.js`, `passport-masar-extension/tests/queue-filter.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/queue-filter.test.js
import { filterQueueSections } from '../src/queue-filter.js';

const records = [
  { id: '1', upload_status: 'processed', masar_status: null, needs_review: false },
  { id: '2', upload_status: 'processed', masar_status: 'submitted', needs_review: false, nusuk_mutamer_id: 'M100' },
  { id: '3', upload_status: 'processed', masar_status: 'failed', needs_review: false },
  { id: '4', upload_status: 'pending', masar_status: null, needs_review: false },
  { id: '5', upload_status: 'failed', masar_status: null, needs_review: false },
  { id: '6', upload_status: 'processed', masar_status: 'submitted', needs_review: true, nusuk_mutamer_id: 'M200' },
  { id: '7', upload_status: 'processed', masar_status: null, needs_review: true },
  { id: '8', upload_status: 'processed', masar_status: null, needs_review: false },
];

describe('filterQueueSections', () => {
  let result;
  beforeAll(() => { result = filterQueueSections(records); });

  test('queue contains processed+null masar (both clean and needs_review)', () => {
    const ids = result.queue.map(r => r.id);
    expect(ids).toEqual(['1', '7', '8']);
  });

  test('needs_review passports ARE in the queue (submittable)', () => {
    const ids = result.queue.map(r => r.id);
    expect(ids).toContain('7');
  });

  test('submitted contains all masar_status=submitted regardless of needs_review', () => {
    const ids = result.submitted.map(r => r.id);
    expect(ids).toEqual(['2', '6']);
  });

  test('failed contains upload_failed and masar_failed', () => {
    expect(result.failed.map(r => r.id)).toEqual(['3', '5']);
  });

  test('pending contains only upload_status=pending', () => {
    expect(result.pending.map(r => r.id)).toEqual(['4']);
  });

  test('every record in exactly one section', () => {
    const all = [...result.queue, ...result.submitted, ...result.failed, ...result.pending];
    expect(all).toHaveLength(records.length);
    expect(new Set(all.map(r => r.id)).size).toBe(records.length);
  });

  test('empty input', () => {
    const r = filterQueueSections([]);
    expect(r).toEqual({ queue: [], submitted: [], failed: [], pending: [] });
  });
});
```

  - Expected Failure: `Cannot find module '../src/queue-filter.js'`

- [ ] **Step 2: Logic Specification**
  - **Signature:** `export function filterQueueSections(records): { queue, submitted, failed, pending }`
  - Priority: (1) either status `'failed'` → `failed`; (2) `masar_status === 'submitted'` → `submitted` (regardless of `needs_review`); (3) `upload_status === 'processed'` AND no `masar_status` → `queue` (regardless of `needs_review` — these are submittable); (4) `upload_status === 'pending'` → `pending`; (5) default → `pending`.
  - Key insight: `needs_review` does NOT change which section a record belongs to. It only affects the badge/color within that section.

- [ ] **Step 3: Verification**
  - `npx jest tests/queue-filter.test.js`

- [ ] **Step 4: Commit**
  - `feat: add queue filter — needs_review stays in queue as submittable`

---

## Task 4: Mutamer Detail URL Builder

- **Files:** `passport-masar-extension/src/mutamer-url.js`, `passport-masar-extension/tests/mutamer-url.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/mutamer-url.test.js
import { buildMutamerDetailUrl, canRedirectToDetail } from '../src/mutamer-url.js';

describe('buildMutamerDetailUrl', () => {
  test('builds from string', () => {
    expect(buildMutamerDetailUrl('M123')).toBe('https://masar.nusuk.sa/mutamer/M123/details');
  });
  test('builds from number', () => {
    expect(buildMutamerDetailUrl(456)).toBe('https://masar.nusuk.sa/mutamer/456/details');
  });
  test('null for empty', () => { expect(buildMutamerDetailUrl('')).toBeNull(); });
  test('null for null', () => { expect(buildMutamerDetailUrl(null)).toBeNull(); });
  test('null for undefined', () => { expect(buildMutamerDetailUrl(undefined)).toBeNull(); });
});

describe('canRedirectToDetail', () => {
  test('true: submitted + mutamer_id', () => {
    expect(canRedirectToDetail({ masar_status: 'submitted', nusuk_mutamer_id: 'M1' })).toBe(true);
  });
  test('false: submitted without mutamer_id', () => {
    expect(canRedirectToDetail({ masar_status: 'submitted', nusuk_mutamer_id: null })).toBe(false);
  });
  test('false: not submitted', () => {
    expect(canRedirectToDetail({ masar_status: null, nusuk_mutamer_id: 'M1' })).toBe(false);
  });
  test('false: failed', () => {
    expect(canRedirectToDetail({ masar_status: 'failed', nusuk_mutamer_id: 'M1' })).toBe(false);
  });
});
```

  - Expected Failure: `Cannot find module '../src/mutamer-url.js'`

- [ ] **Step 2: Logic Specification**
  - `buildMutamerDetailUrl(id)`: falsy → `null`, else → `'https://masar.nusuk.sa/mutamer/' + String(id) + '/details'`
  - `canRedirectToDetail(record)`: `true` only if `masar_status === 'submitted'` AND `nusuk_mutamer_id` is truthy. Only submitted passports are on Nusuk — queue/failed/pending records have nowhere to redirect to.

- [ ] **Step 3: Verification**
  - `npx jest tests/mutamer-url.test.js`

- [ ] **Step 4: Commit**
  - `feat: add Nusuk mutamer detail URL builder`

---

## Task 5: Notification Layer

- **Files:** `passport-masar-extension/src/notifications.js`, `passport-masar-extension/tests/notifications.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/notifications.test.js
import { notify, NOTIFICATION_TYPES } from '../src/notifications.js';

global.chrome = {
  notifications: { create: jest.fn((id, opts, cb) => { if (cb) cb(id); }), clear: jest.fn() },
};
const realNow = Date.now;
beforeEach(() => { jest.clearAllMocks(); Date.now = realNow; });

describe('NOTIFICATION_TYPES', () => {
  test('keys', () => {
    expect(NOTIFICATION_TYPES.CONTEXT_CHANGE).toBe('context_change');
    expect(NOTIFICATION_TYPES.SESSION_EXPIRED).toBe('session_expired');
    expect(NOTIFICATION_TYPES.BATCH_COMPLETE).toBe('batch_complete');
  });

  test('no NEEDS_REVIEW type — not triggered by Nusuk', () => {
    expect(NOTIFICATION_TYPES.NEEDS_REVIEW).toBeUndefined();
  });
});

describe('notify', () => {
  test('creates notification', () => {
    notify(NOTIFICATION_TYPES.BATCH_COMPLETE, 'done');
    expect(chrome.notifications.create).toHaveBeenCalledTimes(1);
    expect(chrome.notifications.create.mock.calls[0][1].message).toBe('done');
  });

  test('dedup within 30s', () => {
    let t = 1000; Date.now = () => t;
    notify(NOTIFICATION_TYPES.SESSION_EXPIRED, 'm');
    t += 10000;
    notify(NOTIFICATION_TYPES.SESSION_EXPIRED, 'm');
    expect(chrome.notifications.create).toHaveBeenCalledTimes(1);
  });

  test('allows after 30s', () => {
    let t = 1000; Date.now = () => t;
    notify(NOTIFICATION_TYPES.SESSION_EXPIRED, 'm');
    t += 31000;
    notify(NOTIFICATION_TYPES.SESSION_EXPIRED, 'm');
    expect(chrome.notifications.create).toHaveBeenCalledTimes(2);
  });

  test('different types not deduped', () => {
    notify(NOTIFICATION_TYPES.SESSION_EXPIRED, 'a');
    notify(NOTIFICATION_TYPES.BATCH_COMPLETE, 'b');
    expect(chrome.notifications.create).toHaveBeenCalledTimes(2);
  });
});
```

  - Expected Failure: `Cannot find module '../src/notifications.js'`

- [ ] **Step 2: Logic Specification**
  - **`NOTIFICATION_TYPES`**: `CONTEXT_CHANGE`, `SESSION_EXPIRED`, `BATCH_COMPLETE`. No `NEEDS_REVIEW` — that's an internal flag, not a Nusuk event.
  - **`notify(type, message, title?)`**: Dedup via `Map<string, number>`, 30s window. `chrome.notifications.create`.

- [ ] **Step 3: Verification**
  - `npx jest tests/notifications.test.js`

- [ ] **Step 4: Commit**
  - `feat: add notification layer — no needs_review notification`

---

## Task 6: Badge Priority Manager

- **Files:** `passport-masar-extension/src/badge.js`, `passport-masar-extension/tests/badge.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/badge.test.js
import { computeBadgeState, applyBadge, BADGE_PRIORITIES } from '../src/badge.js';

global.chrome = { action: { setBadgeText: jest.fn(), setBadgeBackgroundColor: jest.fn() } };
beforeEach(() => jest.clearAllMocks());

describe('computeBadgeState', () => {
  test('session expired wins', () => {
    expect(computeBadgeState({ sessionExpired: true, contextChangePending: true, failedCount: 5 }))
      .toEqual({ text: '!', color: '#D32F2F', priority: 'session_expired' });
  });
  test('context change next', () => {
    expect(computeBadgeState({ sessionExpired: false, contextChangePending: true, failedCount: 5 }))
      .toEqual({ text: '!', color: '#F57C00', priority: 'context_change' });
  });
  test('failed count', () => {
    expect(computeBadgeState({ sessionExpired: false, contextChangePending: false, failedCount: 3 }))
      .toEqual({ text: '3', color: '#D32F2F', priority: 'failed_count' });
  });
  test('clear', () => {
    expect(computeBadgeState({ sessionExpired: false, contextChangePending: false, failedCount: 0 }))
      .toEqual({ text: '', color: '', priority: null });
  });
});

describe('applyBadge', () => {
  test('sets text and color', () => {
    applyBadge({ text: '!', color: '#D32F2F' });
    expect(chrome.action.setBadgeText).toHaveBeenCalledWith({ text: '!' });
    expect(chrome.action.setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#D32F2F' });
  });
});
```

  - Expected Failure: `Cannot find module '../src/badge.js'`

- [ ] **Step 2: Logic Specification**
  - Same as previous. `BADGE_PRIORITIES`, `computeBadgeState`, `applyBadge`.

- [ ] **Step 3: Verification**
  - `npx jest tests/badge.test.js`

- [ ] **Step 4: Commit**
  - `feat: add badge priority manager`

---

## Task 7: Context Change Detection, Debounce, Submission State Machine

- **Files:** `passport-masar-extension/src/context-change.js`, `passport-masar-extension/tests/context-change.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/context-change.test.js
import {
  detectContextChange, applyContextChange,
  hasContextChangePending, clearPendingContextChange, getContextChangeReason,
  createDebouncedContextChecker,
  getSubmissionState, setSubmissionState, shouldStopSubmission, SUBMISSION_STATES,
} from '../src/context-change.js';

const storageData = {};
global.chrome = {
  storage: { local: {
    get: jest.fn((k, cb) => {
      const r = {}; const kl = Array.isArray(k) ? k : (typeof k === 'string' ? [k] : Object.keys(k));
      for (const key of kl) { if (storageData[key] !== undefined) r[key] = storageData[key]; }
      if (cb) cb(r); return Promise.resolve(r);
    }),
    set: jest.fn((o, cb) => { Object.assign(storageData, o); if (cb) cb(); return Promise.resolve(); }),
    remove: jest.fn((k, cb) => { for (const key of (Array.isArray(k) ? k : [k])) delete storageData[key]; if (cb) cb(); return Promise.resolve(); }),
  }},
};

beforeEach(() => { for (const k of Object.keys(storageData)) delete storageData[k]; jest.clearAllMocks(); });

describe('detectContextChange', () => {
  test('null when match', async () => {
    Object.assign(storageData, { masar_entity_id: 'e1', masar_contract_id: 'c1', masar_auth_token: 't1' });
    expect(await detectContextChange({ entity_id: 'e1', contract_id: 'c1', auth_token: 't1' })).toBeNull();
  });
  test('entity_changed', async () => {
    Object.assign(storageData, { masar_entity_id: 'e1', masar_contract_id: 'c1', masar_auth_token: 't1' });
    const r = await detectContextChange({ entity_id: 'e2', contract_id: 'c1', auth_token: 't2' });
    expect(r.reason).toBe('entity_changed');
    expect(storageData.pending_context_change.entity_id).toBe('e2');
  });
  test('contract_changed', async () => {
    Object.assign(storageData, { masar_entity_id: 'e1', masar_contract_id: 'c1', masar_auth_token: 't1' });
    expect((await detectContextChange({ entity_id: 'e1', contract_id: 'c2', auth_token: 't2' })).reason).toBe('contract_changed');
  });
  test('null on first run', async () => {
    expect(await detectContextChange({ entity_id: 'e1', contract_id: 'c1', auth_token: 't1' })).toBeNull();
  });
});

describe('applyContextChange', () => {
  test('writes pending, clears group', async () => {
    Object.assign(storageData, {
      masar_entity_id: 'e1', masar_contract_id: 'c1', masar_auth_token: 't1',
      masar_selected_group: 'g1',
      pending_context_change: { reason: 'entity_changed', entity_id: 'e2', contract_id: 'c2', auth_token: 't2' },
    });
    await applyContextChange();
    expect(storageData.masar_entity_id).toBe('e2');
    expect(storageData.masar_selected_group).toBeUndefined();
    expect(storageData.pending_context_change).toBeUndefined();
  });
});

describe('helpers', () => {
  test('hasContextChangePending', async () => {
    expect(await hasContextChangePending()).toBe(false);
    storageData.pending_context_change = { reason: 'x' };
    expect(await hasContextChangePending()).toBe(true);
  });
  test('getContextChangeReason', async () => {
    expect(await getContextChangeReason()).toBeNull();
    storageData.pending_context_change = { reason: 'contract_changed' };
    expect(await getContextChangeReason()).toBe('contract_changed');
  });
  test('clearPendingContextChange', async () => {
    storageData.pending_context_change = { reason: 'x' };
    await clearPendingContextChange();
    expect(storageData.pending_context_change).toBeUndefined();
  });
});

describe('debounce', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  test('fires after delay with latest', () => {
    const cb = jest.fn();
    const check = createDebouncedContextChecker(cb, 1500);
    check({ entity_id: 'a', contract_id: 'b', auth_token: 'c' });
    check({ entity_id: 'd', contract_id: 'e', auth_token: 'f' });
    jest.advanceTimersByTime(1500);
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith({ entity_id: 'd', contract_id: 'e', auth_token: 'f' });
  });

  test('resets on each call', () => {
    const cb = jest.fn();
    const check = createDebouncedContextChecker(cb, 1500);
    check({ entity_id: 'a', contract_id: 'b', auth_token: 'c' });
    jest.advanceTimersByTime(1000);
    check({ entity_id: 'd', contract_id: 'e', auth_token: 'f' });
    jest.advanceTimersByTime(1000);
    expect(cb).not.toHaveBeenCalled();
    jest.advanceTimersByTime(500);
    expect(cb).toHaveBeenCalledTimes(1);
  });
});

describe('submission state machine', () => {
  test('states', () => {
    expect(SUBMISSION_STATES.IDLE).toBe('idle');
    expect(SUBMISSION_STATES.SUBMITTING_CURRENT).toBe('submitting_current_record');
    expect(SUBMISSION_STATES.QUEUED_MORE).toBe('queued_more_records');
  });
  test('default idle', async () => { expect(await getSubmissionState()).toBe('idle'); });
  test('persists', async () => {
    await setSubmissionState(SUBMISSION_STATES.SUBMITTING_CURRENT);
    expect(await getSubmissionState()).toBe('submitting_current_record');
  });
  test('shouldStop: false no pending', async () => {
    await setSubmissionState(SUBMISSION_STATES.QUEUED_MORE);
    expect(await shouldStopSubmission()).toBe(false);
  });
  test('shouldStop: true pending+idle', async () => {
    storageData.pending_context_change = { reason: 'x' };
    await setSubmissionState(SUBMISSION_STATES.IDLE);
    expect(await shouldStopSubmission()).toBe(true);
  });
  test('shouldStop: false pending+submitting', async () => {
    storageData.pending_context_change = { reason: 'x' };
    await setSubmissionState(SUBMISSION_STATES.SUBMITTING_CURRENT);
    expect(await shouldStopSubmission()).toBe(false);
  });
  test('shouldStop: true pending+queued', async () => {
    storageData.pending_context_change = { reason: 'x' };
    await setSubmissionState(SUBMISSION_STATES.QUEUED_MORE);
    expect(await shouldStopSubmission()).toBe(true);
  });
});
```

  - Expected Failure: `Cannot find module '../src/context-change.js'`

- [ ] **Step 2: Logic Specification**
  - All functions as tested. Single module. `detectContextChange` buffers to `chrome.storage.local`. `createDebouncedContextChecker` closure. `shouldStopSubmission` only allows `submitting_current_record` to continue.

- [ ] **Step 3: Verification**
  - `npx jest tests/context-change.test.js`

- [ ] **Step 4: Commit**
  - `feat: add context change detection, debounce, and submission state machine`

---

## Task 8: Contract Auto-Select

- **Files:** `passport-masar-extension/src/contract-select.js`, `passport-masar-extension/tests/contract-select.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/contract-select.test.js
import { resolveContractSelection } from '../src/contract-select.js';

describe('resolveContractSelection', () => {
  test('null when empty', () => {
    expect(resolveContractSelection([])).toEqual({ selectedContract: null, showDropdown: false });
  });
  test('auto-select single', () => {
    const r = resolveContractSelection([{ id: 'c1', name: 'A', active: true }]);
    expect(r.selectedContract.id).toBe('c1');
    expect(r.showDropdown).toBe(false);
  });
  test('dropdown for multiple', () => {
    const r = resolveContractSelection([
      { id: 'c1', name: 'A', active: true },
      { id: 'c2', name: 'B', active: true },
    ]);
    expect(r.selectedContract).toBeNull();
    expect(r.showDropdown).toBe(true);
  });
  test('filters inactive', () => {
    const r = resolveContractSelection([
      { id: 'c1', name: 'A', active: false },
      { id: 'c2', name: 'B', active: true },
    ]);
    expect(r.selectedContract.id).toBe('c2');
  });
  test('null when all inactive', () => {
    expect(resolveContractSelection([{ id: 'c1', name: 'A', active: false }]))
      .toEqual({ selectedContract: null, showDropdown: false });
  });
});
```

  - Expected Failure: `Cannot find module '../src/contract-select.js'`

- [ ] **Step 2: Logic Specification**
  - Filter `active === true`. 0→`{null,false}`. 1→`{that,false}`. 2+→`{null,true}`.

- [ ] **Step 3: Verification**
  - `npx jest tests/contract-select.test.js`

- [ ] **Step 4: Commit**
  - `feat: add contract auto-select logic`

---

## Task 9: Popup HTML — Four Sections

- **Files:** `passport-masar-extension/src/popup.html`, `passport-masar-extension/tests/popup-structure.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/popup-structure.test.js
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let document;
beforeAll(() => {
  document = new JSDOM(
    fs.readFileSync(path.resolve(__dirname, '../src/popup.html'), 'utf-8')
  ).window.document;
});

describe('popup.html', () => {
  test('context-change-banner hidden', () => {
    const el = document.getElementById('context-change-banner');
    expect(el).not.toBeNull();
    expect(el.hidden || el.classList.contains('hidden')).toBe(true);
  });
  test('confirm + defer buttons', () => {
    expect(document.getElementById('ctx-change-confirm')).not.toBeNull();
    expect(document.getElementById('ctx-change-defer')).not.toBeNull();
  });
  test('home-summary with counts', () => {
    expect(document.getElementById('home-summary')).not.toBeNull();
    expect(document.getElementById('pending-count')).not.toBeNull();
    expect(document.getElementById('failed-count')).not.toBeNull();
  });
  test('queue-section', () => { expect(document.getElementById('queue-section')).not.toBeNull(); });
  test('submitted-section', () => { expect(document.getElementById('submitted-section')).not.toBeNull(); });
  test('failed-section', () => { expect(document.getElementById('failed-section')).not.toBeNull(); });
  test('pending-section', () => { expect(document.getElementById('pending-section')).not.toBeNull(); });
  test('no needs-review-section (merged into submitted)', () => {
    expect(document.getElementById('needs-review-section')).toBeNull();
  });
  test('submit-all-btn', () => { expect(document.getElementById('submit-all-btn')).not.toBeNull(); });
  test('contract-dropdown-container hidden', () => {
    const el = document.getElementById('contract-dropdown-container');
    expect(el).not.toBeNull();
    expect(el.hidden || el.classList.contains('hidden')).toBe(true);
  });
  test('help-support-link', () => { expect(document.getElementById('help-support-link')).not.toBeNull(); });
});
```

  - Expected Failure: Missing DOM elements.
  - **Library:** `jsdom`

- [ ] **Step 2: Logic Specification**
  - Elements:
    1. `div#context-change-banner[hidden]` with `button#ctx-change-confirm`, `button#ctx-change-defer`
    2. `div#home-summary` with `span#pending-count`, `span#failed-count`
    3. `div#contract-dropdown-container[hidden]` with `select#contract-select`
    4. `div#queue-section` — header "قائمة الرفع", card container, `button#submit-all-btn` "رفع الكل"
    5. `div#submitted-section` — header "تم الرفع", card container (holds both clean + needs_review submitted)
    6. `div#failed-section` — header "فشل"
    7. `div#pending-section` — header "قيد المعالجة"
    8. `a#help-support-link` — "مساعدة"
  - No `needs-review-section`. Compact layout.

- [ ] **Step 3: Verification**
  - `npx jest tests/popup-structure.test.js`

- [ ] **Step 4: Commit**
  - `feat: add four-section popup HTML`

---

## Task 10: Popup JS — Card Rendering, Badges, Click-to-Redirect

- **Files:** `passport-masar-extension/src/popup.js`, `passport-masar-extension/tests/popup-queue.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/popup-queue.test.js
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

global.chrome = {
  storage: { local: { get: jest.fn((k, cb) => { if (cb) cb({}); return Promise.resolve({}); }) } },
  runtime: { sendMessage: jest.fn(), onMessage: { addListener: jest.fn() } },
  tabs: { create: jest.fn() },
};

let document;
beforeEach(() => {
  document = new JSDOM(
    fs.readFileSync(path.resolve(__dirname, '../src/popup.html'), 'utf-8')
  ).window.document;
  jest.clearAllMocks();
});

const { renderQueueCard, renderHomeSummary, handleCardClick } = require('../src/popup.js');

describe('renderQueueCard — queue items', () => {
  test('ready card: passport image, name, number, blue badge, submit button', () => {
    const card = renderQueueCard(document, {
      id: '1', full_name: 'أحمد', passport_number: 'A1',
      passport_image_url: 'https://img.test/p.jpg',
      upload_status: 'processed', masar_status: null, needs_review: false,
    });
    expect(card.querySelector('img').src).toBe('https://img.test/p.jpg');
    expect(card.querySelector('img').height).toBeLessThanOrEqual(48);
    expect(card.textContent).toContain('أحمد');
    expect(card.textContent).toContain('A1');
    expect(card.textContent).toContain('جاهز');
    expect(card.querySelector('[data-action="submit"]')).not.toBeNull();
  });

  test('needs_review in queue: amber badge, STILL has submit button', () => {
    const card = renderQueueCard(document, {
      id: '2', full_name: 'سارة', passport_number: 'B2',
      passport_image_url: null,
      upload_status: 'processed', masar_status: null, needs_review: true,
    });
    expect(card.textContent).toContain('يحتاج مراجعة');
    expect(card.querySelector('[data-action="submit"]')).not.toBeNull();
  });
});

describe('renderQueueCard — submitted items', () => {
  test('submitted clean: green badge, no submit, click URL', () => {
    const card = renderQueueCard(document, {
      id: '3', full_name: 'مريم', passport_number: 'C3',
      passport_image_url: 'https://img.test/p3.jpg',
      upload_status: 'processed', masar_status: 'submitted', needs_review: false,
      nusuk_mutamer_id: 'M100',
    });
    expect(card.textContent).toContain('تم الرفع');
    expect(card.querySelector('[data-action="submit"]')).toBeNull();
    expect(card.dataset.clickUrl).toBe('https://masar.nusuk.sa/mutamer/M100/details');
  });

  test('submitted + needs_review: amber badge, no submit, click URL', () => {
    const card = renderQueueCard(document, {
      id: '4', full_name: 'خالد', passport_number: 'D4',
      passport_image_url: null,
      upload_status: 'processed', masar_status: 'submitted', needs_review: true,
      nusuk_mutamer_id: 'M200',
    });
    expect(card.textContent).toContain('تم الرفع - يحتاج مراجعة');
    expect(card.querySelector('[data-action="submit"]')).toBeNull();
    expect(card.dataset.clickUrl).toBe('https://masar.nusuk.sa/mutamer/M200/details');
  });

  test('submitted without mutamer_id: no click URL, unavailable text', () => {
    const card = renderQueueCard(document, {
      id: '5', full_name: 'فهد', passport_number: 'E5',
      passport_image_url: null,
      upload_status: 'processed', masar_status: 'submitted', needs_review: false,
      nusuk_mutamer_id: null,
    });
    expect(card.dataset.clickUrl || '').toBe('');
    expect(card.textContent).toContain('تفاصيل غير متوفرة');
  });
});

describe('renderQueueCard — failed items', () => {
  test('failed: red badge, retry button, no submit', () => {
    const card = renderQueueCard(document, {
      id: '6', full_name: 'نورة', passport_number: 'F6',
      passport_image_url: null,
      upload_status: 'processed', masar_status: 'failed', needs_review: false,
    });
    expect(card.textContent).toContain('فشل');
    expect(card.querySelector('[data-action="retry"]')).not.toBeNull();
    expect(card.querySelector('[data-action="submit"]')).toBeNull();
  });
});

describe('renderQueueCard — pending items', () => {
  test('pending: gray badge, no buttons', () => {
    const card = renderQueueCard(document, {
      id: '7', full_name: 'عمر', passport_number: 'G7',
      passport_image_url: null,
      upload_status: 'pending', masar_status: null, needs_review: false,
    });
    expect(card.textContent).toContain('قيد المعالجة');
    expect(card.querySelector('[data-action="submit"]')).toBeNull();
    expect(card.querySelector('[data-action="retry"]')).toBeNull();
  });
});

describe('renderHomeSummary', () => {
  test('sets counts', () => {
    renderHomeSummary(document, { pendingCount: 8, failedCount: 2 });
    expect(document.getElementById('pending-count').textContent).toBe('8');
    expect(document.getElementById('failed-count').textContent).toBe('2');
  });
});

describe('handleCardClick', () => {
  test('opens tab', () => {
    handleCardClick({ clickUrl: 'https://masar.nusuk.sa/mutamer/M1/details' });
    expect(chrome.tabs.create).toHaveBeenCalledWith({ url: 'https://masar.nusuk.sa/mutamer/M1/details' });
  });
  test('no-op for null', () => {
    handleCardClick({ clickUrl: null });
    expect(chrome.tabs.create).not.toHaveBeenCalled();
  });
  test('no-op for empty', () => {
    handleCardClick({ clickUrl: '' });
    expect(chrome.tabs.create).not.toHaveBeenCalled();
  });
});
```

  - Expected Failure: `renderQueueCard is not a function`

- [ ] **Step 2: Logic Specification**
  - **Signatures:**
    - `export function renderQueueCard(document, record): HTMLElement`
    - `export function renderHomeSummary(document, { pendingCount, failedCount }): void`
    - `export function handleCardClick({ clickUrl }): void`
  - `renderQueueCard`:
    - Passport image `img` (height ≤48, or omit if null)
    - Full name + passport number text
    - Badge from `getStatusLabel(record)` + color from `getStatusColor(record)`
    - **Queue cards** (`processed` + null `masar_status`): submit button regardless of `needs_review`. The `needs_review` flag only changes the badge text/color, NOT the available actions.
    - **Submitted cards** (`masar_status === 'submitted'`): no submit button. If `canRedirectToDetail(record)` → `card.dataset.clickUrl = buildMutamerDetailUrl(...)`. Else → show "تفاصيل غير متوفرة". Badge shows "تم الرفع" (green) or "تم الرفع - يحتاج مراجعة" (amber) based on `needs_review`.
    - **Failed cards**: retry button, no submit.
    - **Pending cards**: no buttons.
  - `handleCardClick`: if `clickUrl` truthy → `chrome.tabs.create`.

- [ ] **Step 3: Verification**
  - `npx jest tests/popup-queue.test.js`

- [ ] **Step 4: Commit**
  - `feat: add card rendering — needs_review submittable in queue, amber badge in submitted`

---

## Task 11: Popup JS — Context Change Banner

- **Files:** `passport-masar-extension/src/popup.js`, `passport-masar-extension/tests/popup-context-change.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/popup-context-change.test.js
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const storageData = {};
global.chrome = {
  storage: { local: {
    get: jest.fn((k, cb) => {
      const r = {}; const kl = Array.isArray(k) ? k : (typeof k === 'string' ? [k] : Object.keys(k));
      for (const key of kl) { if (storageData[key] !== undefined) r[key] = storageData[key]; }
      if (cb) cb(r); return Promise.resolve(r);
    }),
  }},
  runtime: { sendMessage: jest.fn(), onMessage: { addListener: jest.fn() } },
  tabs: { create: jest.fn() },
};

let document;
beforeEach(() => {
  document = new JSDOM(
    fs.readFileSync(path.resolve(__dirname, '../src/popup.html'), 'utf-8')
  ).window.document;
  for (const k of Object.keys(storageData)) delete storageData[k];
  jest.clearAllMocks();
});

const { initContextChangeBanner } = require('../src/popup.js');

describe('context banner', () => {
  test('shown when pending', async () => {
    storageData.pending_context_change = { reason: 'entity_changed' };
    await initContextChangeBanner(document);
    expect(document.getElementById('context-change-banner').hidden).toBe(false);
  });
  test('hidden when no pending', async () => {
    await initContextChangeBanner(document);
    expect(document.getElementById('context-change-banner').hidden).toBe(true);
  });
  test('entity message', async () => {
    storageData.pending_context_change = { reason: 'entity_changed' };
    await initContextChangeBanner(document);
    expect(document.getElementById('context-change-banner').textContent).toContain('تم تغيير الحساب');
  });
  test('contract message', async () => {
    storageData.pending_context_change = { reason: 'contract_changed' };
    await initContextChangeBanner(document);
    expect(document.getElementById('context-change-banner').textContent).toContain('تم تغيير العقد');
  });
  test('confirm sends message', async () => {
    storageData.pending_context_change = { reason: 'entity_changed' };
    await initContextChangeBanner(document);
    document.getElementById('ctx-change-confirm').click();
    expect(chrome.runtime.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'APPLY_CONTEXT_CHANGE' }));
  });
  test('defer hides banner, keeps pending', async () => {
    storageData.pending_context_change = { reason: 'entity_changed' };
    await initContextChangeBanner(document);
    document.getElementById('ctx-change-defer').click();
    expect(document.getElementById('context-change-banner').hidden).toBe(true);
    expect(storageData.pending_context_change).toBeDefined();
  });
});
```

  - Expected Failure: `initContextChangeBanner is not a function`

- [ ] **Step 2: Logic Specification**
  - **Signature:** `export async function initContextChangeBanner(document): void`
  - Read `pending_context_change`. Show/hide banner. Set message from `STRINGS` based on reason. Confirm → `sendMessage`. Defer → hide locally only (pending stays).

- [ ] **Step 3: Verification**
  - `npx jest tests/popup-context-change.test.js`

- [ ] **Step 4: Commit**
  - `feat: add context change banner to popup`

---

## Task 12: Background Script — Full Integration

- **Files:** `passport-masar-extension/src/background.js`, `passport-masar-extension/tests/background-integration.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/background-integration.test.js
global.chrome = {
  storage: { local: {
    get: jest.fn((k, cb) => { if (cb) cb({}); return Promise.resolve({}); }),
    set: jest.fn((o, cb) => { if (cb) cb(); return Promise.resolve(); }),
    remove: jest.fn((k, cb) => { if (cb) cb(); return Promise.resolve(); }),
  }},
  action: { setBadgeText: jest.fn(), setBadgeBackgroundColor: jest.fn() },
  webRequest: { onBeforeSendHeaders: { addListener: jest.fn() } },
  notifications: { create: jest.fn() },
  runtime: { onMessage: { addListener: jest.fn() } },
};

beforeEach(() => jest.clearAllMocks());

describe('background integration', () => {
  test('registers webRequest listener', () => {
    require('../src/background.js');
    expect(chrome.webRequest.onBeforeSendHeaders.addListener).toHaveBeenCalled();
  });

  test('registers runtime message listener', () => {
    require('../src/background.js');
    expect(chrome.runtime.onMessage.addListener).toHaveBeenCalled();
  });

  test('needs_review records are submitted normally — not skipped', () => {
    const { shouldSubmitRecord } = require('../src/background.js');
    // Queue records: processed + null masar_status → always submit
    expect(shouldSubmitRecord({ upload_status: 'processed', masar_status: null, needs_review: false })).toBe(true);
    expect(shouldSubmitRecord({ upload_status: 'processed', masar_status: null, needs_review: true })).toBe(true);
  });

  test('already submitted records are not re-submitted', () => {
    const { shouldSubmitRecord } = require('../src/background.js');
    expect(shouldSubmitRecord({ upload_status: 'processed', masar_status: 'submitted', needs_review: false })).toBe(false);
    expect(shouldSubmitRecord({ upload_status: 'processed', masar_status: 'submitted', needs_review: true })).toBe(false);
  });

  test('pending and failed upload records are not submitted', () => {
    const { shouldSubmitRecord } = require('../src/background.js');
    expect(shouldSubmitRecord({ upload_status: 'pending', masar_status: null, needs_review: false })).toBe(false);
    expect(shouldSubmitRecord({ upload_status: 'failed', masar_status: null, needs_review: false })).toBe(false);
  });

  test('failed masar records are retryable', () => {
    const { shouldSubmitRecord } = require('../src/background.js');
    expect(shouldSubmitRecord({ upload_status: 'processed', masar_status: 'failed', needs_review: false })).toBe(true);
  });
});
```

  - Expected Failure: Depends on current `background.js`.

- [ ] **Step 2: Logic Specification**
  - Modify `background.js`:
    1. Import from `context-change.js`, `badge.js`, `notifications.js`
    2. Debounced context checker at module level
    3. `webRequest` listener: first run → write directly. Otherwise → `debouncedCheck`.
    4. `handleStableContextChange`: `detectContextChange` → update badge → notify only if submission active.
    5. `runtime.onMessage`: `APPLY_CONTEXT_CHANGE` → `applyContextChange()` + badge update.
    6. **Export** `shouldSubmitRecord(record)`:
       - Returns `true` if `upload_status === 'processed'` AND (`masar_status` is null/undefined OR `masar_status === 'failed'`)
       - Returns `false` otherwise
       - `needs_review` has NO effect on this function — it is always ignored for submission decisions
    7. Submission loop: iterate records, call `shouldSubmitRecord` per record, skip if false. Between records call `shouldStopSubmission()` for context-change gating. Set submission states (`SUBMITTING_CURRENT` / `QUEUED_MORE` / `IDLE`). After batch → `notify(BATCH_COMPLETE, ...)`.

- [ ] **Step 3: Verification**
  - `npx jest tests/background-integration.test.js`

- [ ] **Step 4: Commit**
  - `feat: integrate background — needs_review submitted normally, no special handling`

---

## Task 13: Manifest — Notifications Permission

- **Files:** `passport-masar-extension/manifest.json`, `passport-masar-extension/tests/manifest.test.js`

- [ ] **Step 1: Test Contract**

```javascript
// tests/manifest.test.js
const manifest = JSON.parse(require('fs').readFileSync(
  require('path').resolve(__dirname, '../manifest.json'), 'utf-8'
));

describe('manifest.json', () => {
  test('notifications', () => { expect(manifest.permissions).toContain('notifications'); });
  test('storage', () => { expect(manifest.permissions).toContain('storage'); });
  test('MV3', () => { expect(manifest.manifest_version).toBe(3); });
});
```

  - Expected Failure: `notifications` may be missing.

- [ ] **Step 2: Logic Specification**
  - Add `"notifications"` to `permissions` if absent.

- [ ] **Step 3: Verification**
  - `npx jest tests/manifest.test.js`

- [ ] **Step 4: Commit**
  - `chore: add notifications permission`

---

## Task 14: Telegram — Rewrite Message Texts

- **Files:** `passport-telegram/bot/messages.py`, `passport-telegram/tests/test_messages_text.py`

- [ ] **Step 1: Test Contract**

```python
# tests/test_messages_text.py
from bot.messages import (
    welcome_text, help_text, format_masar_status_text,
    SUPPORT_CONTACT_TEXT,
    quota_exceeded_text, user_blocked_text, processing_error_text,
)


class TestWelcomeText:
    def test_action_leads(self):
        lines = [l.strip() for l in welcome_text().strip().split('\n') if l.strip()]
        assert not any(l.startswith('/') for l in lines[:5])

    def test_order(self):
        t = welcome_text()
        assert t.find("صور") < t.find("/token") < t.find("/masar")

    def test_no_platform(self):
        assert "مسار" not in welcome_text().replace("/masar", "")

    def test_no_support(self):
        assert SUPPORT_CONTACT_TEXT not in welcome_text()


class TestHelpText:
    def test_action_leads(self):
        lines = [l.strip() for l in help_text().strip().split('\n') if l.strip()]
        assert not any(l.startswith('/') for l in lines[:5])

    def test_no_platform(self):
        assert "مسار" not in help_text().replace("/masar", "")

    def test_has_support(self):
        assert SUPPORT_CONTACT_TEXT in help_text()

    def test_has_commands(self):
        assert "/token" in help_text() and "/masar" in help_text()


class TestFormatMasarStatusText:
    def test_no_platform(self):
        r = [{"full_name": "أحمد", "passport_number": "A1", "status": "pending"}]
        assert "مسار" not in format_masar_status_text(r).replace("/masar", "")

    def test_name_and_number(self):
        r = [
            {"full_name": "أحمد محمد", "passport_number": "A123", "status": "pending"},
            {"full_name": "سارة علي", "passport_number": "B456", "status": "failed"},
        ]
        t = format_masar_status_text(r)
        assert "أحمد محمد" in t and "A123" in t
        assert "سارة علي" in t and "B456" in t

    def test_empty_done(self):
        t = format_masar_status_text([])
        assert len(t.strip()) > 0

    def test_no_support(self):
        assert SUPPORT_CONTACT_TEXT not in format_masar_status_text(
            [{"full_name": "x", "passport_number": "y", "status": "submitted"}]
        )


class TestSupportPlacement:
    def test_quota(self): assert SUPPORT_CONTACT_TEXT in quota_exceeded_text()
    def test_blocked(self): assert SUPPORT_CONTACT_TEXT in user_blocked_text()
    def test_error(self): assert SUPPORT_CONTACT_TEXT in processing_error_text()
```

  - Expected Failure: Current texts have "مسار", wrong structure, wrong support placement.

- [ ] **Step 2: Logic Specification**
  - `welcome_text()`: action-sequence lead. No "مسار". No `SUPPORT_CONTACT_TEXT`.
  - `help_text()`: action lead + command ref. Append `SUPPORT_CONTACT_TEXT`. No "مسار".
  - `format_masar_status_text(records)`: full name + passport number. No "مسار". Empty → done msg.
  - `quota_exceeded_text()`, `user_blocked_text()`, `processing_error_text()`: append `SUPPORT_CONTACT_TEXT`.
  - Remove `SUPPORT_CONTACT_TEXT` from all other functions.

- [ ] **Step 3: Verification**
  - `pytest passport-telegram/tests/test_messages_text.py -v`

- [ ] **Step 4: Commit**
  - `feat: rewrite Telegram texts — action-led, no platform names, restricted support`

---

## Dependency Graph & Execution Order

```
1 (Strings) ──────────────────────────────────┐
  ├─→ 2 (Status)                              │
  ├─→ 7 (Context Change)                      │
  └─→ 9 (Popup HTML) ←────────────────────────┘

2 (Status) ──→ 10 (Popup Cards)
3 (Queue Filter) ──→ 10
4 (Mutamer URL) ──→ 10

5 (Notifications) ──→ 12 (Background)
6 (Badge) ──→ 12
7 (Context Change) ──→ 11, 12

9 (Popup HTML) ──→ 10, 11

8 (Contract Select) ── standalone
13 (Manifest) ── standalone
14 (Telegram) ── standalone
```

**Execute in this order:**

1. **Task 1** (Strings)
2. **Tasks 2, 3, 4, 5, 6, 8** (parallel)
3. **Task 7** (Context Change)
4. **Task 9** (Popup HTML)
5. **Tasks 10, 11** (parallel)
6. **Task 12** (Background)
7. **Tasks 13, 14** (parallel)

---

Task list complete. Feed the following Markdown into your local agent for implementation.