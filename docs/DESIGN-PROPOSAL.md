# Design Proposals — passport-masar-extension Popup Redesign

Three structurally distinct proposals for the extension popup. Each uses a different information architecture, not just a different color palette. Open the companion HTML files in a browser to review visually.

---

## Proposal 1 — "Single Card Wizard"

**File:** `design-proposal-1.html`

### Design direction

One card that morphs. The popup is one unified surface — a large hero header that changes color and content per state, plus a body area below. There are no "screen transitions." The hero gradient shifts to signal state: amber (setup), green (active), red (error/expiry), orange (context change).

### Key structural decisions

- **Onboarding:** Full-bleed hero with step number, icon, and subtitle. One action per screen. Progress communicated through a subtle bar inside the hero, not a separate stepper component. The hero's color shift provides subconscious state awareness.
- **Main queue:** The hero collapses into a compact "status strip" — one line showing entity, group, contract badge. All queue space goes to content. No separate context panel eating vertical space.
- **Queue cards:** Compact "mini-cards" — one row per person. Avatar (36px) + name/passport + status text + action button + dismiss, all inline. Status communicated through a colored right-border (3px) — green=ready, amber=processing, red=failed. No status badges consuming horizontal space.
- **Submit all:** Inside the body, not a separate sticky bar. The queue is short enough that scrolling to it is natural.
- **Contract expired:** The status strip turns red with an "expired" badge. Banner explains. Queue visible but fully grayed out. The red strip is impossible to miss.
- **Context change:** Hero turns orange. Two buttons in the body. No queue visible — the decision is the only thing on screen.

### Why this direction

Travel agency staff scan fast. They open the popup, glance at the top color (green = fine, red = problem, orange = needs decision), and act. The hero-as-state-indicator is the most information-dense first impression possible. The compact mini-cards maximize the number of records visible without scrolling in the 320px popup.

### Trade-offs

- The hero takes vertical space during onboarding (but onboarding is a one-time flow).
- Mini-cards sacrifice avatar size for density — face crops are small (36px).
- No per-card detail expansion in this proposal. Detail review would need a separate view later.

---

## Proposal 2 — "Dense Panel"

**File:** `design-proposal-2.html`

### Design direction

Everything on one screen. No screen transitions at any point in the user journey. Onboarding is a checklist, not separate screens. The queue is a table, not cards. Dark mode for long-session comfort.

### Key structural decisions

- **Onboarding as checklist:** Three steps shown as a vertical checklist. Step 1 starts expanded (shows the token input). Steps 2 and 3 show as pending single-line items. When step 1 is completed, it collapses to a single line with a checkmark, and step 2 expands. The user always sees the full journey — no "where am I?" confusion.
- **Queue as table rows:** No cards. Each passport is a grid row: status indicator (4px colored bar) + name/passport + status label + action button. All in one horizontal line. This fits 5-6 records without scrolling.
- **No avatars in the queue.** Face crops consume ~40px of horizontal space per row. In a 340px popup with dense layout, that space is better used for name legibility and action buttons. Face crops can live in a detail view.
- **Context as accordion:** Entity/group/contract info lives in a single-line collapsible accordion at the top. Collapsed: shows entity dot + summary text. Expanded: shows all four context rows. This gives context when needed without permanent vertical cost.
- **Fixed bottom bar:** Submit-all is always visible at the bottom, separated by a border. No need to scroll past records to find it.
- **Error codes inline:** Failed records show the error code (e.g., "403") directly in the passport number line, not in a separate error message div. Saves vertical space.

### Why this direction

Some agencies process 20-50 passports per session. For them, the extension is a work tool, not a guided experience. Dense layout means more records visible, less scrolling, faster triage. The checklist onboarding respects their time — they can see all three steps at once and know what's coming.

Dark mode is a deliberate choice: these staff work on monitors for hours. Reduced brightness is easier on the eyes and gives the tool a professional feel without being intimidating.

### Trade-offs

- No avatars means less visual identity per record. Users rely on name + passport number alone.
- Checklist onboarding shows all steps at once, which could overwhelm a first-time user — though the collapsed/expanded pattern mitigates this.
- The table layout is less "friendly" than cards. This is a professional tool, not a consumer app.
- Dark mode may feel unfamiliar to users who associate dark UIs with developer tools.

---

## Proposal 3 — "Conversational Flow"

**File:** `design-proposal-3.html`

### Design direction

The extension talks to you. The entire UI is structured as a vertical message thread — like a chat between the user and the system. Onboarding steps are assistant messages with embedded forms. Queue records are "incoming" message bubbles. Status updates are system notices.

### Key structural decisions

- **Chat header:** Looks like a messaging app header — avatar, name ("تسجيل المعتمرين"), and a status line that updates per state ("بانتظار ربط الحساب" → "متصل بمنصة نسك" → "جارٍ الرفع…"). The status line is the primary state indicator.
- **Onboarding as conversation:** Step 1 is a white system bubble that says "أرسل /token في تيليجرام، ثم الصق الرمز هنا" with an embedded input and button. When completed, it collapses to a centered notice ("✓ تم ربط الحساب") and the next step appears as a new message below. The conversation history stays visible — the user can see their progress.
- **Queue records as incoming bubbles:** Each passport appears as a green incoming message bubble (WhatsApp-style) with embedded passport card (avatar + name + passport number), status badge, and action buttons. Failed records get a red left-border on their bubble.
- **Quick replies at the bottom:** "Submit all" lives in a bottom bar styled as quick reply buttons (like Telegram bot keyboards). Context change decisions also use this quick-reply pattern.
- **Pinned context bar:** Between the header and the message area, a thin pinned bar shows entity + contract info. Like a pinned message in a group chat.
- **System notices for transitions:** Completed onboarding steps, queue summaries ("3 جوازات معلقة"), and status changes appear as centered system notices (like "User joined the group" messages in chat apps).

### Why this direction

The users already live in Telegram. They send passport photos in Telegram, run /token in Telegram, check /masar in Telegram. A chat-like interface in the extension creates continuity between the two tools — same mental model, different surface.

The conversational structure also solves the "what do I do next?" problem naturally. Each system message is a prompt for exactly one action. The conversation flows downward. There's no need to figure out which screen you're on — you just read the latest message and respond.

The assistant's "voice" (e.g., "ممتاز! الآن افتح منصة نسك") provides warmth and guidance without a heavy UI framework.

### Trade-offs

- Chat bubbles are less space-efficient than table rows or mini-cards. Fewer records visible without scrolling.
- The conversational metaphor may feel odd to users who expect a traditional form-based extension. Not all interactions map naturally to "messages."
- The background pattern (subtle grid lines) adds visual texture but consumes rendering resources on low-end machines — can be removed.
- Settings screen breaks the metaphor (it's a plain form, not a conversation). Could be addressed by making settings a "system message with editable fields" but that adds complexity.

---

## Comparison Matrix

| Dimension | P1: Single Card Wizard | P2: Dense Panel | P3: Conversational Flow |
|---|---|---|---|
| **Screen transitions** | Hero morphs, no page change | None — everything on one view | None — messages append |
| **Onboarding model** | One step per hero | Collapsible checklist | System messages with forms |
| **Queue layout** | Mini-cards (1 row each) | Table rows (grid) | Chat bubbles |
| **Records visible (no scroll)** | ~4-5 | ~5-6 | ~2-3 |
| **Face crop avatar** | Yes (36px) | No | Yes (38px) |
| **State indicator** | Hero color shift | Checklist + accordion dot | Header status line |
| **Theme** | Light, warm amber | Dark, teal accents | Light, sage green |
| **Best for** | Fast glance-and-act | High-volume processing | First-time / low-tech users |
| **Weakest at** | Detail review | Friendliness | Information density |

---

## Recommended next step

Review the HTML files in a browser. Each shows all screens in sequence. Pick the direction that best matches how the agency staff actually work — then the implementation can mix elements across proposals (e.g., P2's table density with P1's hero color signaling).
