# Brainstorming Refined

Historical design notes for the extension UI redesign.

This file is no longer an implementation checklist. The old task-by-task brainstorm content was removed because it referenced stale paths and pre-approval ideas that no longer match the worktree.

## Canonical References

- Approved spec: `docs/superpowers/specs/2026-03-31-extension-ui-redesign-design.md`
- Approved plan: `docs/superpowers/plans/2026-03-31-extension-ui-redesign.md`
- Preserved final proposal mock: `docs/final-design-proposal.html`
- Current implementation: `passport-masar-extension/popup.html`, `passport-masar-extension/popup.css`, `passport-masar-extension/popup.js`, `passport-masar-extension/background.js`

## What Landed In The Worktree

- The popup was rebuilt into a tabbed workspace with Pending, In Progress, Submitted, and Failed sections.
- The main screen now uses a compact summary strip, contract selector, context-change banner, and section counts.
- Batch submission uses `chrome.storage.session` state and drains records sequentially.
- `needs_review` records can submit directly and keep an amber badge after submission.
- Submitted records can open the Nusuk detail page through `masar_detail_id` when available.
- Badge priority and Chrome notifications now cover session expiry, context changes, batch completion, and failed counts.

## Early Ideas That Were Not Kept

- A large multi-scene proposal set is no longer the active design contract.
- The popup is not a full FAQ/contact center or image-heavy review console.
- The archived brainstorms should not be used to derive file paths, module names, or implementation steps.

## Use This File For

- Understanding how the redesign discussion evolved before the approved spec/plan were finalized.
- Tracing which high-level ideas survived into the implemented extension.

Do not use this file as a task list or as a file-path reference.
