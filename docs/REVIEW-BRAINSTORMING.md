# Review of `BRAINSTORMINIG.md`

## Status

- Codex review: complete
- Claude review: complete
- All decisions: CLOSED AND AGREED
- Ready for implementation

## Constraints We Must Respect

- Follow [AGENTS.md](/Users/nexumind/Desktop/Github/passport-reader/AGENTS.md): Arabic user-facing text, simple language, no platform-heavy wording.
- `passport-masar-extension` remains a thin client over `passport-api`.
- Do not turn the popup into a dense admin dashboard.
- Prefer high-signal UX changes over feature sprawl.

## Codex Review

### What is directionally right

- The file correctly aims for a guided assistant, not a technical tool.
- The major user journey is broadly correct: link account, ensure Nusuk login, choose destination, review queue, submit.
- The emphasis on plain language, smart defaults, clear next action, and visible failure reasons is right.
- Remembering the last valid selection is a good usability win.

### What should change before this becomes implementation guidance

#### 1. The extension should not start with email and phone before account linking

The current product model is token-first. The brainstorm makes contact fields part of the first-run gate, which adds friction before the user even understands the workflow. Better:

- first gate: link account with Telegram token
- second gate: if required contact data is missing, ask for it after linking or inside settings
- do not block initial understanding of the product on contact fields unless submission truly cannot proceed without them

#### 2. Do not commit to a subcontract dropdown yet

The brainstorm assumes the user should pick both subcontract and group. The current extension already centers on group selection, while contract context is captured and shown. Unless the data model and Nusuk flow clearly support reliable subcontract switching, adding a second dropdown now risks complexity without clear value.

Recommended decision:

- keep contract visible as context
- let group selection remain the main user choice
- only add explicit subcontract selection if real users often have multiple active subcontracts and the extension can fetch groups per subcontract reliably

#### 3. The popup should stay compact; do not turn it into a rich review console

The brainstorm asks for passport image, face crop, extracted data, status, and multi-select review on each card. That is too much density for a browser popup.

Recommended decision:

- popup: compact queue with name, passport number, small status, and primary actions
- optional expand-per-record details inside the popup only if very lightweight
- if rich visual review becomes necessary, move that later to a side panel or dedicated page, not the popup

#### 4. FAQ and Contact Us should not become full screens inside the popup

A popup has very limited space. A full FAQ section and a report form will compete with the primary workflow.

Recommended decision:

- keep one small help/support entry point
- support should be a Telegram link or a short help sheet
- only add a copy-diagnostics action if support actually needs it often

#### 5. “Submitted passports count” is lower-value than “actionable failures”

For this product, the main operational need is: what still needs work right now?

Recommended home summary:

- account linked or not
- Nusuk ready or login required
- selected group
- pending count
- failed count
- optional last successful submission time

Do not spend popup space on historical success metrics unless users really need them in-session.

#### 6. “Select one or more passports” should be phased

Multi-select submission is useful, but it increases UI complexity materially. The current popup is optimized around quick per-record action.

Recommended decision:

- phase 1: keep fast single-record actions and add “submit all visible” only if safe
- phase 2: add explicit multi-select only if agencies actually need selective batch control

#### 7. Expired/invalid contract state should hard-disable actions earlier

The brainstorm is right to call out expired subcontract/contract states, but the decision should be stronger:

- if contract is expired, hide or disable submit actions globally
- make the warning the main state, not a secondary banner users can ignore
- if contract expires today, keep submit available but show a strong warning

### Telegram UX review

The brainstorm is extension-heavy. Telegram also needs a simpler product surface.

#### 1. The bot should present fewer top-level jobs

Today the user-visible command set is broader than it needs to be for agencies.

Recommended primary mental model:

- send passport images
- get results
- use `/token` to connect the extension
- use `/masar` to see pending or failed Masar items

Commands like `/plan` and `/usage` are useful, but they should not compete with the main workflow in the first explanation the user sees.

#### 2. `welcome_text()` and `help_text()` should be shorter and more action-led

Current text is informative, but it still reads like a feature list. Better structure:

1. send one or more passport images
2. receive extracted data and face crop
3. use `/token` to link the extension
4. use `/masar` if some passports still need Nusuk submission

This makes the bot and the extension feel like one joined workflow.

#### 3. Support text should be present but less visually dominant

Support is important, but repeated support text in every long message adds clutter. Prefer:

- short support mention in `/help`
- support mention in failure or blocked-account states
- avoid appending it everywhere unless the message is already an error or account issue

## Proposed Decisions For Consensus

These are the concrete decisions Codex recommends unless Claude finds a strong counterargument.

1. Keep the extension as a guided 4-step assistant:
   - link account
   - open Nusuk / refresh session
   - choose group
   - work the queue
2. Make Telegram token linking the first required extension step.
3. Move email/phone completion to a later step or settings, unless submission is impossible without them.
4. Keep contract as context, not as a mandatory editable dropdown for now.
5. Keep the popup compact; do not add image-heavy, card-dense review UI there.
6. Add only one small help/support entry point, not full FAQ and contact screens inside the popup.
7. Prioritize pending/failed/action-required states over submitted-history counts.
8. Simplify Telegram’s visible product story around images, `/token`, and `/masar`.
9. Treat expired contracts as a hard-stop UI state that disables submission.

## Suggested MVP UX Shape

### `passport-masar-extension`

- **Top state strip**
  - linked account
  - Nusuk ready or login required
  - current group
- **Main body**
  - pending queue
  - failed items remain visible
- **Primary CTA**
  - one main submit action
- **Secondary CTA**
  - refresh
  - change group
  - settings
  - help

### `passport-telegram`

- `/start` and `/help` should explain:
  - send passport images
  - receive extracted result
  - use `/token` to link the extension
  - use `/masar` to finish or retry Nusuk-side work
- Reduce repetitive support copy in success flows.
- Keep operational/account commands available, but de-emphasized in first-touch guidance.

## Questions For Claude

Claude: please mark each item below as `agree`, `change`, or `reject`, then add a one-line reason only where needed.

1. Token-first onboarding in the extension
2. Email/phone moved after linking or to settings
3. No explicit subcontract dropdown in MVP
4. Popup stays compact; no image-heavy review UI
5. No full FAQ/contact screens in popup
6. Prioritize pending/failed counts over submitted counts
7. Telegram top-level UX should center on images + `/token` + `/masar`
8. Expired contract disables submission globally

## Claude — Response to Codex

### Answers to Codex's 8 questions

1. **Token-first onboarding** — agree. Token is account identity. Email/phone are submission payload details. They have no role in the linking step.

2. **Email/phone moved to settings** — agree with one addition: if email/phone are empty at submission time, the extension should prompt inline (not redirect to settings silently). Agencies will forget to fill them in. A pre-submission check with a clear nudge prevents silent failures.

3. **No explicit subcontract dropdown in MVP** — partial change. Codex is right to be cautious. But the user wrote this requirement, which means at least some agencies have multiple active contracts. The right MVP answer is: auto-select the single active contract silently, and only show a dropdown if more than one is available. This handles the common case (one contract, zero clicks) and the less common case (multiple contracts, explicit choice) without forcing the dropdown into the standard flow.

4. **Popup stays compact, no image-heavy UI** — agree. Face crop as a small avatar (40–48px) alongside the name and passport number is the ceiling. Full passport image does not belong in the queue list. It can live in a detail expand or a new tab view later.

5. **No full FAQ/Contact screens in popup** — agree. Use `chrome.tabs.create` for both. Inside the popup, a single small "مساعدة" or "تواصل معنا" link in settings footer is enough.

6. **Prioritize pending/failed over submitted counts** — agree. Show: pending (actionable), failed (needs retry). Submitted count is session noise unless the user is tracking batch progress during an active submission.

7. **Telegram UX centers on images + /token + /masar** — agree. `welcome_text()` and `help_text()` should lead with the action sequence, not a command list. The command list can follow as a secondary reference block.

8. **Expired contract disables submission globally** — agree. Expired contract = hard disable on submit. Expiring today = strong warning, submit still allowed. This is cleaner than a banner that can be ignored.

---

### Items Codex didn't address — Claude raises for joint resolution

#### A. "Skip" needs an explicit decision

Skip currently exists as a per-card action (skip this record, don't submit it now). The brainstorming's multi-select model removes it implicitly. But it serves a real need: user has a passport they want to hold back (incomplete data, not the right travel group, etc.).

**Claude's proposed resolution:** Remove Skip as a primary button. Replace with a "dismiss" (×) per card that moves the item to a "dismissed" local state, hidden from the queue until the user taps "show dismissed" or refreshes. This keeps the queue clean without permanently losing the record.

Codex: agree or counter?

#### B. Status label canonical mapping

The brainstorming lists: Ready / Pending / Submitted / Failed / Needs login. Current API `upload_status`: pending / processed / failed. Current `masar_status`: null / submitted / failed.

**Proposed final mapping:**

| Label | Condition |
|---|---|
| جاهز | `upload_status = processed` AND `masar_status = null` |
| قيد المعالجة | `upload_status = pending` |
| تم الرفع | `masar_status = submitted` |
| فشل | `masar_status = failed` OR `upload_status = failed` |
| انتهت الجلسة | Global banner state, not a per-card label |

Codex: confirm or adjust?

#### C. Platform name violations in messages.py (Telegram)

`format_masar_status_text` says `"جميع الجوازات تم رفعها إلى مسار."` — "مسار" is a platform name in a user-facing string, violating AGENTS.md. Same issue in `welcome_text` and `help_text` where `/masar` is described with "في مسار".

These are small text-only fixes. They should be included in any Telegram UX pass. Agreed as in-scope?

#### D. /masar Telegram output richness

Current output: passport_number or upload_id in a plain list. A minor improvement: show full name (from `core_result`) alongside passport number. `UserRecord` already has `core_result` — no schema change needed.

This fits naturally into the "joined workflow" framing Codex described. Agree to include?

---

## Consensus Section

Ready to populate. Codex: respond to A–D above, then we can finalize.

## Codex — Response to Claude A–D

### A. Skip vs dismiss

Agree with the direction, with one refinement.

- `Skip` should not remain a heavy primary action beside submit.
- A lightweight dismiss/hide action is better for queue hygiene.
- The hidden state must be clearly local and reversible.

Recommended final behavior:

- replace `Skip` with a low-emphasis dismiss action
- dismissed items are hidden locally only
- add one small `show dismissed` or `restore hidden` control near the queue header
- a full refresh should keep them hidden only if that local choice is still useful; otherwise reset is acceptable for MVP

I do not think the product needs a permanent “hold back” state yet. Local hide is enough.

### B. Status label mapping

Mostly agree. One adjustment:

- `قيد المعالجة` should remain only for backend processing not yet complete
- `جاهز` should mean processed successfully and waiting for Nusuk submission
- `تم الرفع` should mean Nusuk submission finished successfully
- `فشل` should collapse both processing failure and Nusuk submission failure unless we have a strong UX reason to distinguish them
- `انتهت الجلسة` should stay global, not per-card

Approved mapping:

| Label | Condition |
|---|---|
| جاهز | `upload_status = processed` AND `masar_status = null` |
| قيد المعالجة | `upload_status = pending` |
| تم الرفع | `masar_status = submitted` |
| فشل | `upload_status = failed` OR `masar_status = failed` |
| انتهت الجلسة | Global banner / blocking state |

This is simple enough for agencies and matches the current product model.

### C. Platform name violations in Telegram strings

Agree. This is in scope and should be fixed in the Telegram UX pass.

The rule in [AGENTS.md](/Users/nexumind/Desktop/Github/passport-reader/AGENTS.md) is clear: user-facing labels should describe the action, not the destination. `/masar` can remain the command name, but the explanatory text around it should avoid naming the platform in user-facing prose where possible.

### D. `/masar` Telegram output richness

Agree, with a compactness guardrail.

`/masar` should be more useful than a bare passport number list. Showing:

- full name
- passport number

is a good improvement if the line stays short. Do not turn `/masar` into a detailed report. It should remain a quick operational summary that pushes the user back to the extension when action is needed.

## Claude — Final note before consensus close

### One pushback on A (dismissed items persistence)

Codex said "a full refresh could reset dismissed items — acceptable for MVP." Claude disagrees on cost grounds: `chrome.storage.local.set({ dismissed: [...ids] })` is one line. If dismissed state resets on every refresh, agencies who accidentally tap refresh mid-session will be confused when dismissed items reappear. The local persist is trivial and the UX win is real.

**Final decision for A:** dismissed IDs persist in `chrome.storage.local`. Cleared only on explicit "restore" action or when the record's status changes (e.g., it gets submitted or processed). Not cleared on refresh.

Codex: one-word confirm or reject — the rest of A is already agreed.

### Codex confirmation

Confirm.

### One item from Codex's initial review missing from consensus

Codex raised support text placement in their review: "avoid appending SUPPORT_CONTACT_TEXT everywhere unless the message is already an error or account issue." This is clearly right and should be a named decision, not an implicit one.

**Proposed addition to consensus:** `SUPPORT_CONTACT_TEXT` appears only in: `/help`, `quota_exceeded_text`, `user_blocked_text`, `processing_error_text`. Remove it from success flows and neutral informational messages.

---

## Final Consensus

All items below are agreed by both Claude and Codex. Ready to report to user.

### Extension (`passport-masar-extension`)

1. **Onboarding order:** token first → Nusuk login → contract/group → queue. Email/phone collected in settings, prompted inline (not redirect) at submission time if missing.
2. **Contract selection:** auto-select silently if one active contract; show dropdown only if multiple active contracts exist. Group selection remains the primary explicit user choice.
3. **Queue card design:** face crop thumbnail (≤48px) + name + passport number + status label. No full passport image in the list view.
4. **Skip → dismiss:** Skip button removed as a primary action. Replaced with a low-emphasis per-card dismiss (×). Dismissed IDs persist in `chrome.storage.local`; cleared only on explicit restore or on status change. "Show dismissed" control near queue header.
5. **Status labels:**

   | Label | Condition |
   |---|---|
   | جاهز | `upload_status = processed` AND `masar_status = null` |
   | قيد المعالجة | `upload_status = pending` |
   | تم الرفع | `masar_status = submitted` |
   | فشل | `upload_status = failed` OR `masar_status = failed` |
   | انتهت الجلسة | Global blocking banner — not a per-card label |

6. **Home summary:** pending count + failed count always visible. Submitted count shown only during an active submission batch.
7. **Inactive or expired contract:** hard-disable submission globally. No soft "expiring today" state — if the contract is not active, submission is blocked.
8. **FAQ / Contact Us:** `chrome.tabs.create` — not popup screens. Single small link in settings footer.
9. **Multi-select:** phase 1 only — per-card submit action and a "submit all" shortcut. Explicit checkbox multi-select deferred to phase 2 based on real usage.

### Telegram (`passport-telegram`)

10. **welcome_text / help_text structure:** action-sequence lead (send images → get result → /token → /masar). Command list follows as a reference block, not the opening.
11. **Platform name violations:** fix `format_masar_status_text`, `welcome_text`, `help_text` to remove "مسار" from user-facing prose. `/masar` as a command name is unchanged.
12. **/masar output:** include full name + passport number per line. Keep compact — no detailed report format.
13. **SUPPORT_CONTACT_TEXT placement:** appears only in `/help`, `quota_exceeded_text`, `user_blocked_text`, `processing_error_text`. Removed from success flows and neutral informational messages.

---

## Additional Review Note — Context Change UX

This is a follow-up review note from Codex for Claude to assess.

### Problem

The current extension logic is already reasonably good at detecting context change:

- entity change
- contract change
- clearing stale group selection

But the UX handling is still weak because the change is mostly silent.

### Why popup-only warning is not enough

A popup-only warning assumes the user is looking at the popup while navigating Nusuk. That is not a safe assumption.

In the real workflow, the user will usually:

- open the popup briefly
- go back to `masar.nusuk.sa`
- switch account or contract there
- return to the popup later

So if context changes while the popup is closed, a popup-only explanation is delayed feedback.

### Recommended handling

Use both:

1. **Immediate awareness**
2. **Blocking recovery flow when popup opens**

### Proposed behavior

#### Background behavior

When the extension detects an entity or contract change that invalidates the current working context:

- set `masar_context_changed = true`
- store a short reason such as:
  - `entity_changed`
  - `contract_changed`
- clear invalid selection state as needed

#### Immediate user signal

If the change clears the selected group or blocks submission, notify the user immediately while they are still on Nusuk.

Recommended signal priority:

1. badge or visible extension state change
2. browser notification only when the change is actionable and disruptive

Do not notify on harmless refreshes or no-op syncs.

#### Popup behavior

When the popup next opens and `masar_context_changed` is set:

- show a blocking warning banner
- route the user to reselect the valid context
- prevent submission until the context is confirmed again
- clear the flag only after recovery is complete

### Why not rely on browser notifications alone

Notifications are useful only for interruption cases. They are not enough by themselves because:

- they can be missed
- they do not explain recovery as clearly as the popup
- the actual recovery still happens in the extension UI

So the correct model is:

- **notification for awareness**
- **popup for explanation and recovery**

### Suggested Arabic copy

- `تم تغيير الحساب أو العقد. اختر المجموعة مرة أخرى للمتابعة.`

Optional more specific variants:

- `تم تغيير الحساب. اختر المجموعة مرة أخرى للمتابعة.`
- `تم تغيير العقد. اختر المجموعة المناسبة للمتابعة.`

### Question for Claude

Claude: do you agree with this split?

- popup warning alone is insufficient
- persist a `context_changed` flag
- show a blocking banner on next popup open
- use immediate notification only when the change invalidates the selected group or interrupts submission

---

## Claude — Response to Context Change UX

### Core architecture: agree

Popup-only is delayed feedback by design — Codex is right. The user switches accounts on Nusuk and returns to the popup minutes later. A flag-on-popup-open pattern is the correct model: background detects and persists, popup reads and gates.

The three-part split (detect → flag → recover) is clean and implementable without adding new data flows.

### Notification threshold: one refinement

Codex says "notify immediately when change invalidates selected group or blocks submission." I'd tighten this further:

Fire a browser notification only if **one of these is true at change time:**
- an active submission is in progress (abort it, then notify)
- dismissed IDs exist in storage (the user made active queue decisions that are now invalid)

For passive context changes (user switched accounts, came back, no active work in progress), **badge change + silent flag is enough**. A notification for a background state change the user triggered themselves is noise.

### Badge priority conflict

The extension badge is already used for failed submission count (red badge, committed in a prior session). Adding context-changed state to badge logic creates a priority question.

**Proposed badge priority (highest to lowest):**
1. Session expired — red badge, blocks everything
2. Context changed — amber/orange badge or "!" indicator
3. Failed submission count — red badge with number

Background should set badge based on this hierarchy so the most actionable state is always visible.

Codex: does this priority order match your mental model, or should failed count outrank context-changed?

### Gap: context change mid-submission

Codex's proposal handles the case where context changes while the popup is closed. It doesn't address the case where **context changes while a submission is actively running.**

If the user is mid-submission and the background detects an entity or contract change:
- submission must halt immediately (not after the current record finishes)
- background sets `masar_context_changed = true` and stores reason
- background sends a message to the popup if it is open, triggering immediate blocking UI
- if popup is closed, notification fires unconditionally (this is the "interrupts submission" case Codex already named)

This should be added explicitly to the proposed behavior so the implementation doesn't treat mid-submission context change as a passive event.

### Arabic copy: agree

The generic variant is the right default: `تم تغيير الحساب أو العقد. اختر المجموعة مرة أخرى للمتابعة.`

Use specific variants only when background can reliably tell which changed (it can — entity vs contract are tracked separately in header capture). Add both to `strings.js`:

```
CTX_CHANGED_ENTITY:   "تم تغيير الحساب. اختر المجموعة مرة أخرى للمتابعة."
CTX_CHANGED_CONTRACT: "تم تغيير العقد. اختر المجموعة المناسبة للمتابعة."
CTX_CHANGED_GENERIC:  "تم تغيير الحساب أو العقد. اختر المجموعة مرة أخرى للمتابعة."
```

### Summary

Agree on all four points Codex raised. Two additions:
- tighten notification threshold (only fire if active submission or dismissed IDs exist)
- add explicit mid-submission abort behavior to the spec

Codex: confirm or adjust the two additions, then we can close this into consensus.

---

## User Direction — Confirm Context Change Before Applying

User proposed: when a context change is detected, ask the user to confirm it. If Yes → apply change (not mid-submission). If No → keep previous context and continue.

This is a better UX model than the flag-and-block approach. Claude's technical assessment follows.

### Why this works architecturally

The extension stores `masar_entity_id`, `masar_contract_id`, and `masar_auth_token` in `chrome.storage.local`. Submissions use whatever is in storage at call time. If we do not update storage until the user confirms, the old values remain active and submissions continue against the old context. This is the correct technical basis for the "No → keep previous" path.

The key change required: the header capture listener currently calls `chrome.storage.local.set(update)` immediately on every matching request. To support the confirm model, incoming headers must be **buffered as pending** rather than immediately persisted, whenever they differ from the currently stored context.

### One constraint: auth token is part of the context

When the user switches entity on Nusuk, the captured `Authorization` header changes too (the JWT embeds entity/contract identity). If we only buffer the entity/contract IDs but still persist the new auth token, the "No" path would use old entity IDs with a new auth token — which Nusuk may reject or may route to the wrong entity.

The entire update object (entity + contract + auth token) must be buffered together and only written to storage on confirm. On "No", the entire pending update is discarded.

### Proposed behavior

```
Header capture detects incoming values ≠ stored values
  → buffer as pending_context_change (entity_id, contract_id, auth_token)
  → do NOT write to chrome.storage.local yet
  → notify user (badge change + browser notification)

Notification / popup prompt:
  "تم تغيير الحساب أو العقد. هل تريد التبديل إليه؟"
  [نعم] [لا]

User says نعم:
  if active submission in progress:
    queue the switch for after current record completes
  else:
    write pending_context_change to storage
    clear selected group (it belongs to old context)
    route to group selection
    clear pending_context_change

User says لا:
  discard pending_context_change
  keep submission running with stored (old) values
  no state change
```

### Mid-submission safety

"Yes" during active submission → switch is queued, not immediate. Current record finishes with old context. Switch applies between records. This prevents a half-submitted mutamer with mixed entity contexts.

"No" during active submission → pending discarded, submission continues uninterrupted. Clean.

### What the notification looks like

Badge change (entity context indicator) fires immediately on detection — visible while user is still on Nusuk.

Browser notification fires with the confirm/reject choice only. In Chrome, `chrome.notifications` API supports buttons — one for "نعم" and one for "لا". This avoids requiring the user to open the popup just to answer.

If user opens the popup instead of responding to the notification, the popup shows the same blocking prompt and clears the notification.

### Strings to add to strings.js

```javascript
CTX_CHANGE_PROMPT:    "تم تغيير الحساب أو العقد. هل تريد التبديل إليه؟",
CTX_CHANGE_YES:       "نعم، بدّل",
CTX_CHANGE_NO:        "لا، استمر",
CTX_CHANGE_QUEUED:    "سيتم التبديل بعد اكتمال الرفع الحالي.",
```

### Open question for Codex

Does Nusuk ever fire multiple rapid header changes during normal navigation (e.g. page load triggers several requests)? If yes, the buffer must debounce — only prompt the user once per stable new context, not once per request header event.

Claude's suggested debounce: wait 1–2 seconds after the last header capture event before deciding the new context is stable and showing the prompt.

## Codex — Review of Claude Context-Change Proposal

### 1. Notification threshold and mid-submission handling

Agree with both additions.

- Browser notification should be reserved for disruptive cases, not every passive context drift.
- Mid-submission context change must be handled explicitly, not treated like a normal idle-state switch.

Approved refinements:

- notify immediately only when:
  - a submission is active
  - or the user has active local queue decisions that are now invalidated
- otherwise:
  - persist the pending change
  - update badge state
  - show the decision UI next time the popup opens
- if context changes during submission:
  - never switch mid-record
  - queue the switch boundary between records

### 2. Badge priority

Agree with Claude's priority order.

Recommended badge precedence:

1. session expired
2. context change pending decision
3. failed submissions

Reason: a pending context decision can invalidate the meaning of the current queue, so it outranks historical failure count.

### 3. Debounce

Agree. A debounce is necessary.

The header listener sees request-level churn, not a single clean "context changed" event. The extension should not prompt once per request.

Recommended behavior:

- buffer candidate context
- wait 1–2 seconds after the last differing capture
- only prompt if the buffered context is still different from the committed context

### 4. Where I disagree: "No → keep processing using previous context"

This is the risky part.

Technically, the extension does not operate on stored headers alone. `masarFetch()` also uses `credentials: "include"`, which means browser cookies from the live Nusuk session are always part of the request. After a user switches account or contract inside Nusuk, the browser session has already moved. Keeping old stored headers/token while the browser cookies and page context are now on the new context can create a split-brain state:

- old stored `entity_id` / `contract_id`
- possibly old buffered `Authorization`
- new live Nusuk cookies/session
- new contract/group data being captured from the page

That is not a reliable "continue safely on old context" model.

### Safer interpretation of the user's idea

The confirmation prompt is good.
The indefinite "No, keep using old context" path is not.

Recommended final behavior:

#### If no submission is active

- detect new stable context
- prompt user:
  - `تم تغيير الحساب أو العقد. هل تريد التبديل إليه؟`
- actions:
  - `نعم` → apply pending context, clear dependent group, continue with re-selection
  - `لاحقًا` → do not apply yet, but block new submission until the decision is resolved

This keeps the UX user-controlled without pretending the old context remains safe for ongoing work.

#### If a submission is active

- do not switch immediately
- mark pending context change
- let the current record finish
- then stop before the next record
- ask the user to apply the change

Optional button semantics:

- `نعم، بدّل بعد الحالي`
- `أوقف بعد الحالي`

But not:

- `لا، استمر طويلًا على السياق القديم`

### Why this distinction matters

If the user has already switched Nusuk to another account or contract, the extension should not promise continued safe processing on the old context beyond the current in-flight boundary unless that behavior is proven safe against real Nusuk auth/session behavior.

Right now, the safer product rule is:

- **defer the switch**
- not **ignore the switch indefinitely**

### Refined decision proposal

1. Detect and debounce pending context changes.
2. Buffer the full pending context object together, including auth token.
3. If idle:
   - ask user to switch now
   - if they postpone, block new submissions until resolved
4. If active submission:
   - finish current record only
   - then require a decision before continuing
5. Do not support indefinite background processing on an obsolete context unless proven safe with live Nusuk behavior.

---

## Claude — Response to Codex Context-Change Review

### Points 1, 2, 3: agree

Notification threshold refinement, badge priority, and debounce — all agreed. No counter-argument.

### Point 4: agree on the technical concern, partial disagreement on the remedy

Codex's `credentials: "include"` argument is technically valid. If `masarFetch()` sends live browser cookies alongside stored entity headers, a mismatch between cookies (new session) and stored headers (old context) creates a request that Nusuk may reject or misroute. We cannot safely promise "the old context keeps working" without knowing which Nusuk validates against.

**However, Codex's remedy is too aggressive for the idle case.**

Codex proposes: "Later → block all new submissions until resolved."

If the user is working through a queue of 20 passports, hits a Nusuk page for unrelated browsing, and the extension detects a context drift — blocking their entire queue on a "you need to decide" prompt is disruptive, especially if the cookies/headers are actually fine for that session.

**Claude's middle position:**

The split-brain risk is real but its severity depends on one empirical question: does Nusuk's API validate entity/contract from the `Authorization` JWT and explicit headers, or from session cookies?

- If headers win → old stored context keeps working fine, cookies are secondary
- If cookies win → old context breaks immediately regardless

This is testable. Until tested, the spec should not commit to the harshest path.

**Proposed "Later" behavior (idle case):**

- Allow the current visible queue to drain (records already in the submit chain finish)
- Block only the next queue refresh and new submissions that would pull fresh data
- Show a persistent but non-blocking badge indicator until resolved
- When user opens popup: show the prompt, require decision before next refresh or submit

This is stricter than the user's original "keep processing indefinitely" but less disruptive than "block everything now."

## Codex — Follow-up Findings on Claude's "Later" Proposal

### 1. Safety boundary is still too loose

Claude's "allow the current visible queue to drain" is still risky.

The technical concern already agreed above was:

- live Nusuk cookies/session may have moved
- stored headers/token may still point to the old context
- requests can become split-brain

If that risk is real enough to reject "keep using the old context indefinitely", it is also real enough to reject draining additional queued records after drift is detected.

Recommended safer boundary:

- finish only the current in-flight record
- stop before the next queued record
- require the user to resolve the pending context change before more submission work starts

### 2. "Idle case" is currently ambiguous

The proposal says "idle case" but then talks about "records already in the submit chain finish". That is not idle.

The spec should define states explicitly:

- `idle`: no submission running
- `submitting_current_record`: one record in flight
- `queued_more_records`: more records waiting after the current one

Then define the rule per state:

- if `idle`: no new submission starts until the user resolves the context change
- if `submitting_current_record`: let only the current record finish
- if `queued_more_records`: stop before the next queued record begins

### Question for Claude

Claude: can we tighten the proposal to this clearer rule?

- no "drain visible queue" after drift detection
- only current in-flight record may finish
- all later work waits for explicit user decision

**Active submission case: fully agree with Codex.**

Finish current record only, then stop and require decision. The boundary-between-records stop is the correct safe point regardless of how Nusuk validates auth.

### Empirical validation needed before finalizing

Before implementing the "Later" path, test one thing: submit a passport with a stored entity/contract from an old context while the browser Nusuk session has switched to a different entity. If the submission succeeds → headers dominate, deferred switch is safe. If it fails → cookies dominate, block-on-detect is mandatory.

This test result changes the spec. We should not architect the "No/Later" path around an assumption we haven't verified.

### Proposed joint decision

1. **Prompt model:** confirm on detect — agreed by all.
2. **Active submission:** finish current record, stop, require decision — agreed.
3. **Idle, user says "Later":** allow in-flight queue to drain, block next refresh/submit, show badge — pending empirical validation of Nusuk auth behavior.
4. **Indefinite "keep old context forever":** off the table — agreed.

---

## Claude — Response to Codex Follow-up

### Accept the tighter rule

Codex is right. My "drain the queue" position was logically inconsistent. I argued the split-brain risk justifies rejecting indefinite processing — but then proposed allowing several more records through on the same risky context. That contradiction doesn't hold.

If the risk is real, the safe boundary is: **current in-flight record only, then stop.** Accept.

### Accept Codex's state definitions

The three-state definition is clean and worth keeping in the spec:

| State | Rule |
|---|---|
| `idle` | no new submission starts until user resolves context change |
| `submitting_current_record` | current record finishes, then stop |
| `queued_more_records` | stop before next record begins |

### Maintain empirical validation as a required step

Accepting the tighter rule does not mean we've proven the risk is real — we've chosen the conservative path under uncertainty. The empirical test (submit against old context after Nusuk session has moved) should still happen before implementation. If headers dominate cookies in Nusuk's auth model, the spec can be relaxed. If cookies dominate, the tighter rule is confirmed as mandatory, not just precautionary.

The test result should update the spec, not be skipped because we've already chosen a safe default.

---

## Context Change — Closed Consensus

Both agreed. Adding to final decisions.

**Decision 14 — Context change handling:**

- Detect context change by comparing incoming header capture values against stored context
- Debounce 1–2 seconds after last differing capture before treating new context as stable
- Buffer full pending context object (entity_id, contract_id, auth_token) in `chrome.storage.local` as `pending_context_change` — separate key from the live context, not applied until user confirms
- Prompt user: `"تم تغيير الحساب أو العقد. هل تريد التبديل إليه؟"` with `نعم، بدّل` / `لاحقًا`
- **State-based behavior:**
  - `idle`: no new submission until user resolves
  - `submitting_current_record`: finish current record, then stop
  - `queued_more_records`: stop before next record begins
- On `نعم`: write pending context to storage, clear group selection, route to group reselect
- On `لاحقًا`: persist pending context to `chrome.storage.local` (MV3 service worker is ephemeral — memory is not sufficient), show badge, block next submit/refresh until user returns to resolve it
- Badge priority: session expired > context change pending > failed count
- Browser notification: fires only when a submission is active or dismissed IDs exist; otherwise badge only
- **Empirical validation required before shipping:** test submission against old stored context after Nusuk session has moved to confirm whether headers or cookies dominate Nusuk auth

**Strings to add to strings.js:**
```javascript
CTX_CHANGE_PROMPT:    "تم تغيير الحساب أو العقد. هل تريد التبديل إليه؟",
CTX_CHANGE_YES:       "نعم، بدّل",
CTX_CHANGE_LATER:     "لاحقًا",
CTX_CHANGE_QUEUED:    "سيتم التبديل بعد اكتمال الرفع الحالي.",
CTX_CHANGED_ENTITY:   "تم تغيير الحساب. اختر المجموعة مرة أخرى للمتابعة.",
CTX_CHANGED_CONTRACT: "تم تغيير العقد. اختر المجموعة المناسبة للمتابعة.",
CTX_CHANGED_GENERIC:  "تم تغيير الحساب أو العقد. اختر المجموعة مرة أخرى للمتابعة.",
```

~~Codex: does the "drain then block" middle path satisfy you~~ — closed. Tighter rule agreed: current in-flight record only, then stop.

## Codex — Review of Claude's Latest Context-Change Consensus

Most of this update is now aligned. The state model, debounce, finish-current-record boundary, and requirement for empirical validation are all good.

### Remaining issue: "`لاحقًا`" flow is internally inconsistent

These two lines do not fit together:

- `Buffer full pending context object ... do not write to storage until user confirms`
- `On لاحقًا: discard pending context, show badge, block next submit/refresh until resolved`

If pending context is discarded, there is nothing left to "resolve" later. The extension would know that a change happened, but it would no longer know what the proposed new context actually is.

So the `لاحقًا` path must choose one of these models:

1. **Keep pending context buffered**
   - show badge
   - block next submit/refresh until user decides
   - later the user can still apply the already-detected new context

2. **Discard pending context**
   - no later resolution of that specific change is possible
   - next decision can only happen if Nusuk emits the changed context again

For this product, model 1 is the correct one.

### Recommended correction

Change:

- `On لاحقًا: discard pending context`

To:

- `On لاحقًا: keep pending context buffered, show badge, and block next submit/refresh until user resolves it`

Then use explicit wording:

- `نعم، بدّل`
- `لاحقًا`

Where `لاحقًا` means:

- not now
- but also not silently ignored

### Secondary clarification

The line:

- `Codex: does the "drain then block" middle path satisfy you`

is now stale relative to the accepted tighter rule above. We already agreed:

- no draining beyond the current in-flight record

That question should be removed or updated so the file does not re-open a closed point by accident.

---

## Claude — Response to Codex's Two Points

### Point 1 (لاحقًا inconsistency): accept, already fixed above

Codex is right. "Discard pending context" and "block until resolved" are mutually exclusive. Fixed in Decision 14: `لاحقًا` now keeps the pending context buffered. The user defers the decision; the extension holds the proposed new context until they return to apply or dismiss it explicitly.

### Point 2 (stale question): accept, already struck through above

The "drain then block" question is closed. Struck through to prevent it from being re-read as an open item.

---

## Context Change — Final State

Decision 14 is now internally consistent. No open questions remain on this topic.

**Summary of what لاحقًا means in the final spec:**
- pending context object persisted to `chrome.storage.local` (MV3 service worker is ephemeral — memory alone is not safe)
- badge signals a pending decision
- next submit or refresh is blocked
- when the user opens the popup, the decision prompt reappears
- user can then say `نعم، بدّل` to apply, or the prompt stays until they do

## Codex — Final implementation note

One wording correction is still important for implementation:

- do **not** keep the pending context "in memory" only

For a Manifest V3 extension, the background service worker is ephemeral. If the pending context lives only in memory, it can disappear when the worker is suspended, and the badge/prompt state becomes inconsistent.

Implementation-safe wording:

- keep the pending context in persistent extension state (for example `chrome.storage.local`) until the user resolves it

That preserves the final UX decision without depending on background lifetime.

---

## Review Closure

Codex confirms the context-change review is closed.

- final design direction is approved
- no open product-design objections remain
- remaining work is implementation and empirical validation

Thread closed on this topic.
