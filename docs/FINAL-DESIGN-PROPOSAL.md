# Final Design Proposal — passport-masar-extension Popup

This document selects one final direction from the three popup redesign proposals and turns it into a concrete design to build.

## Canonical Design Artifacts

Use these as the only active design references:

- written proposal: `docs/FINAL-DESIGN-PROPOSAL.md`
- canonical HTML mock: `docs/final-design-proposal.html`

## Archived Explorations And Duplicate Mocks

The following files are archived under `docs/archive/design-exploration/` and should not be used as the active implementation target:

- `DESIGN-PROPOSAL.md`
- `design-proposal-1.html`
- `design-proposal-2.html`
- `design-proposal-3.html`
- `final-design-review.html`

Notes:

- `final-design-review.html` was a trimmed review variant of the final mock, so it duplicated the final direction and risked drift.
- `DESIGN-PROPOSAL.md` and `design-proposal-1/2/3.html` were exploratory variants used to choose the direction, not the final build target.

## Decision

Use **Proposal 1: Single Card Wizard** as the base design.

Borrow one structural element from **Proposal 2: Dense Panel**:

- make the **main queue denser**
- keep the **setup and state transitions simple and obvious**

Do **not** use Proposal 3 as the main direction. The conversational model is distinctive, but it wastes too much vertical space for a small working popup.

## Why This Direction

This extension is a work tool, not a dashboard and not a chat app.

The user needs to know three things quickly:

1. what state the extension is in
2. what action is needed next
3. whether records are ready to raise, blocked, or need review

Proposal 1 is the best fit because it makes state obvious. The popup should feel like one controlled surface that changes mood and instruction based on state, instead of a stack of unrelated screens.

Proposal 2 contributes one useful improvement: the queue should be tighter and more operational. Once setup is complete, the popup becomes a work surface, so record rows should use space carefully.

## Product Goals

- Make setup, relink, and login problems immediately understandable
- Keep the queue fast to scan in a narrow popup
- Separate backend relink from external login clearly
- Keep Arabic copy short, direct, and non-technical
- Preserve the feeling of one tool, not many disconnected screens

## Final Information Architecture

The popup remains a **single-card flow** with distinct states.

### State 1: Setup

Shown when no backend token is stored.

Content:

- strong title for account linking
- one token input
- one primary action
- one short inline error area

Behavior:

- this is also the destination for **relink required**
- relink messaging stays inside setup instead of using a separate expired-session screen

### State 2: External Login Required

Shown when the external session is missing or invalid.

Content:

- one status banner
- one action button to open the login page

Behavior:

- this state is only for external session problems
- it must never be used for revoked backend sessions

### State 3: Group Selection

Shown when linking is complete and external context exists, but no group is selected.

Content:

- one short instruction block
- one select control
- one primary confirm button

Behavior:

- keep this state minimal
- if groups cannot load because backend auth is gone, route back to setup
- if groups cannot load because external login is gone, route to external login required

### State 4: Main Queue

Shown when account linking, external context, and group selection are all ready.

Layout:

- compact top status strip
- short contract warnings below it when needed
- dense record list below

The old large context panel should evolve toward a tighter summary strip rather than a full information block that permanently consumes height.

Recommended strip content:

- account summary
- group summary
- contract state pill
- one refresh action
- one settings action if needed

### State 5: Settings

This remains separate and secondary.

It should not define the product experience. It is a utility panel, not a primary workflow surface.

## Visual Direction

### Chosen Aesthetic

Use a **warm operational editorial** style.

This should feel:

- serious enough for daily agency work
- distinct from generic admin dashboards
- human and grounded, not glossy or futuristic

The memorable design trait should be the **state header**: a strong, warm, color-led top surface that changes the mood of the popup immediately.

### Core Style

- Light theme
- Warm, grounded palette
- Strong state color at the top of the card
- Clear Arabic typography
- Subtle texture instead of flat color fields

### State Signaling

Use color as the first-layer status signal:

- amber: setup or incomplete linking
- green: ready and operational
- red: blocking problem
- orange: warning or context change

This should happen in the top card area or status strip, not through many separate badges.

### Palette

Use a restrained earthy palette, not default SaaS blue and not purple gradients.

Suggested base tokens:

- sand background
- ivory card surface
- olive-green ready state
- brass-amber setup state
- clay-red blocking state
- burnt-orange warning state
- ink-brown primary text

The queue area should stay calm and readable. Color intensity belongs mostly in the top state area and in narrow status accents, not across every surface.

### Typography

Use an Arabic-first pair with more character than a default product font.

Recommended direction:

- display and headings: **Tajawal**
- body and dense UI text: **IBM Plex Sans Arabic**

The tone should feel operational, not playful and not developer-oriented.

### Motion

Motion should be small but intentional.

Use:

- a short header-color transition when state changes
- a slight upward fade for banners and queue rows on load
- crisp hover and press feedback on row actions

Do not add chat-like animations, continuous pulsing loaders, or decorative motion that slows down work.

### Density Rule

Use Proposal 1 spacing for setup and error states.

Use Proposal 2 density for the queue:

- tighter rows
- less wasted vertical spacing
- actions visible without feeling cramped

## Final Queue Design

The queue should not use a full chat-bubble layout and should not become a table-heavy admin panel.

Use **compact rows or mini-cards** with:

- passenger name
- passport number
- review status
- primary action
- secondary skip action

Recommended behavior:

- no large avatars in the queue
- keep review state visible but compact
- keep error messaging short and inline
- keep per-row actions immediate, not hidden behind extra taps

Recommended row structure:

- top line: passenger name
- second line: passport number plus short secondary context
- side accent or small status chip for review or submission state
- primary action and subdued secondary action on the same row

Each row should feel like a compact work item, not a chat bubble and not a spreadsheet line.

This is the one place where Proposal 2 is the better model than Proposal 1.

## Auth-State Mapping

This branch work already established the correct behavioral split. The final design should preserve it explicitly.

### Backend Auth Invalid

Examples:

- token revoked
- token replaced by a new link
- unknown backend token

UI response:

- clear stored backend token
- return user to **Setup**
- show short relink guidance

This is not a login problem. It is a linking problem.

### External Session Invalid

Examples:

- external session expired
- user is logged out externally
- external headers or session cannot be read

UI response:

- show **External Login Required**
- keep the user’s backend link intact
- offer one action to open the login page

This is not a relink problem.

## Copy Rules

Follow repo rules strictly:

- all user-facing text in Arabic
- no platform names in user-facing labels
- describe the action, not the destination

Examples of the final copy direction:

- relink: "انتهت جلسة الربط — الصق رمزًا جديدًا"
- external login: "جلسة الدخول غير متاحة — افتح صفحة الدخول وسجّل الدخول"
- action button: "افتح صفحة الدخول"

## Recommended Component Model

Build the popup around these visual units:

1. `state-header`
2. `inline-banner`
3. `setup-form`
4. `login-action-panel`
5. `group-picker`
6. `queue-summary-strip`
7. `queue-row`
8. `settings-panel`

This keeps the UI easy to reason about and avoids screen-specific duplication.

## Implementation Styling Notes

Use CSS variables from the start. Suggested token groups:

- colors
- radius
- shadows
- spacing
- transition durations

Suggested visual rules:

- rounded but not toy-like corners
- strongest shadow only under the main card
- subtle texture or pattern in the header only
- borders used sparingly, mainly to organize dense areas
- one dominant primary button style across the popup

## What To Remove From Earlier Proposals

- Do not use the conversational message-thread structure from Proposal 3
- Do not use full dark mode from Proposal 2 as the default
- Do not keep the permanently tall context panel from the current popup
- Do not merge relink and login into one generic expired-session UI

## Implementation Priorities

### Phase 1

- refactor the popup into the final state model
- replace the tall context block with a compact status strip
- keep the current auth-state split intact

### Phase 2

- tighten queue rows for better density
- polish warning and contract states
- unify spacing, buttons, and banners across all states

### Phase 3

- optional motion polish for state transitions
- optional detail expansion for record-level review if needed later

## Recommendation

The final popup should be:

- **Proposal 1 in structure**
- **Proposal 2 in queue density**
- **not Proposal 3 in metaphor**

In short: **one clear card, one clear state, one compact operational queue.**
