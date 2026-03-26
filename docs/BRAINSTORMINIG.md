## UI/UX Process Workflow Requirements

### Product goal

Refine `passport-masar-extension` as simple, guided extension workflow for non-technical users and agencies so they can:

* connect their Nusuk account,
* choose the correct subcontract and group,
* review pending passports,
* submit selected passports,
* understand status clearly at every step.

The interface must feel like a guided assistant, not a technical tool.

---

## 1) Core user journey

### Step 1: Connect account

The user opens the extension and sees a simple onboarding flow.

The extension asks for:

* email
* phone number
* country code

TO BE USED IN Mutamer Submitation

then it asks for:
* Telegram token
The user gets the token from the Telegram bot and pastes it into the extension. or direct him to t.me/raf3_aljawazat_bot and instruct him to use /token command

Success state:

* account is linked
* the extension shows the agency/user as connected

---

### Step 2: Login to Nusuk

The user logs in to Nusuk in the browser.

The extension detects the active Nusuk session and loads:

* current subcontracts
* groups under each subcontract

The user does not need to understand technical details such as sessions, cookies, or APIs.

---

### Step 3: Choose subcontract and group

The extension shows two dropdowns:

* Subcontract
* Group

Behavior:

* if there is only one subcontract, auto-select it
* if there is only one group, auto-select it
* remember the last selected subcontract and group
* reload groups when subcontract changes

This is the main decision step for the user.
Indicate Expired(not active) subcontract.

---

### Step 4: Review pending passports

The extension shows a list of pending passports.

Each passport card should display:

* passport image
* cropped face image if available
* basic extracted data
* status

Status labels should be simple:

* Ready
* Pending
* Submitted
* Failed
* Needs login

The user should be able to select one or more passports for submission.

---

### Step 5: Submit

The user clicks one main button:

* Submit selected passports

During submission, the extension shows:

* progress count
* success count
* failure count

After submission:

* successful passports are marked as submitted
* failed passports remain visible with a clear reason
* user can retry failed items

---

## 2) Main UI structure

### Home screen

The home screen must be simple and focused.

It should show:

* connection status
* Nusuk login status
* selected subcontract
* selected group
* pending passports count
* submitted passports count
* failed passports count

Primary action:

* Submit selected passports

Secondary actions:

* Refresh data
* Change subcontract/group
* Retry failed
* Help

---

### Settings

Settings must be minimal and easy to understand.

Include only:

* notifications on/off
* default subcontract
* default group
* auto-refresh data
* logout

Do not expose technical settings such as:

* tokens
* cookies
* API details
* queue settings
* debug options

---

### FAQ

Add a simple FAQ section for common agency questions.

Suggested FAQ topics:

* How do I connect my account?
* Why do I need to log in to Nusuk?
* How do I choose a group?
* What does Pending mean?
* Why did a passport fail?
* Can I close Nusuk after setup?
* What should I do if login expires?

Answers must be short, plain, and non-technical.

---

### Contact Us

Add a visible support area for agencies.

Include:

* Telegram support
* report a problem form

Optional:

* copy diagnostic info button for support use only

---

## 3) UX principles

The product must follow these rules:

* Use plain language.
* Show only the next action the user needs.
* Hide technical complexity.
* Use smart defaults.
* Remember previous selections.
* Give clear success and failure states.
* Avoid overwhelming the user with too many options.
* Make it obvious what to do next at all times.

---

## 4) Required edge cases

### Nusuk session expired

If the login expires:

* stop submission immediately
* show: “Your Nusuk login expired. Please log in again.”
* require the user to re-login
* reload subcontract and group data after login

This is a hard stop.

---

### No subcontract found

If no subcontract is available or expired:

* show a clear empty/expired( expired by nusak) state
* disable submission
* tell the user to check their Nusuk account access

---

### No group found

If the selected subcontract has no groups:

* show: “No group found. Please create one in Nusuk and refresh.”
* disable submission until a valid group exists

---

### Passport submission failure

If a passport fails:

* keep it visible
* show the failure reason
* allow retry

Do not hide failed items.

---

### Network interruption

If the network fails:

* pause the process
* show that the action is paused
* allow the user to retry after connection returns

---

### Duplicate submission

If a passport is already submitted:

* show it as submitted
* prevent accidental re-submission unless the user retries manually

---

## 5) Data and state requirements

The extension should maintain clear states:

* Unlinked
* Linked
* Nusuk login required
* Nusuk active
* Subcontracts loaded
* Groups loaded
* Group selected
* Passports pending
* Ready to submit
* Submitting
* Submitted
* Failed
* Session expired
* Re-login required

---

## 6) Content tone requirements

All UI text must be:

* short
* direct
* non-technical
* easy for agencies to understand

Examples of good labels:

* Connect account
* Choose subcontract
* Choose group
* Pending passports
* Submit selected
* Login expired
* Refresh data
* Retry failed

Avoid technical labels such as:

* session token
* API auth
* worker queue
* backend sync
* request header

---

## 7) Final workflow summary

```text
Connect account
→ Log in to Nusuk
→ Load subcontract(s) and group(s)
→ Select subcontract
→ Select group
→ Review pending passports
→ Submit selected passports
→ Track success/failure
→ Re-login only when Nusuk session expires
```

---

## 8) Product positioning

This should feel like:

* a guided assistant for agencies
* a simple submission dashboard
* a non-technical workflow tool

Not like:

* a developer tool
* a technical integration panel
* a browser automation utility.