# passport-masar-extension

## Scope

- This package is a plain Manifest V3 extension, not WXT.
- Keep background logic restart-safe and explicit.
- Prefer explicit request/response flows over passive observers.

## User-facing strings

- All agency-visible strings stay in `strings.js`.
- Keep user-facing Arabic short, direct, and non-technical.
- Developer logs, error tags, and debug payloads stay English.

## Critical Masar auth findings

- Do not assume `pms-tk_session` is the correct bearer token for every Masar endpoint.
- The live Masar tab can hold multiple token classes at once:
  - `pms-tk_session`
  - `pms-ref_tk_session`
  - `pms-tk_perm_session`
  - `pms-usr_tk_session`
- For `GetContractList`, the known-good token shape was `tokenType: 5`.
- In captured failing cases, `pms-tk_session` was a broader `tokenType: 3` token with:
  - `defaultEntityId`
  - `defaultEntityTypeId`
  - `activeRecordId`
  - `recordId`
  - large `entities[]`
- That broader token can conflict with the active entity headers and lead to unstable `520` responses.

## Token selection rule

- When syncing from the live Masar tab, read all four token candidates.
- Prefer `pms-usr_tk_session` when present and valid.
- Reject any token whose decoded payload conflicts with the active entity context from:
  - `pms-ac_En_Id`
  - `pms-ac_En_Type_Id`
- Never use `pms-ref_tk_session` as the request bearer token.
- Treat `tokenType: 5` as the strongest candidate for entity-scoped contract discovery.

## Contract-list request rule

- `GetContractList` must be sent with:
  - active entity headers
  - empty `contractid`
- Do not leak the currently selected contract into contract discovery requests.

## Context resolution rule

- Do not let the popup independently decide:
  - selected contract
  - whether the contract banner shows
  - whether the dropdown shows
- Use the resolver in `context-change.js` after every fresh contract fetch.
- The resolver is the source of truth for these outcomes:
  - one selectable contract: auto-select, no banner
  - multiple selectable contracts: show picker and keep confirmation pending
  - zero selectable contracts: clear contract selection and show plain unavailable message

## Storage/debugging hints

- Active entity is taken from session storage:
  - `pms-ac_En_Id`
  - `pms-ac_En_Type_Id`
- Current contract is usually mirrored in local storage `currentContract`.
- `active_ui_context` is the normalized runtime source of truth.
- Legacy `masar_*` keys are derived mirrors used by older code paths.

## Details clone rule

- A cloned details tab is only valid if the captured source snapshot has usable session auth.
- Do not proceed with a clone when the captured snapshot has:
  - no `sessionEntries`
  - no usable auth token in session storage
- In that case, fall back to reusing the live Masar tab instead of opening a degraded clone.
- Treat unconfirmed details outcomes as failure, not success. `unknown` is not a valid terminal success state.

## Submission resume rule

- `SUBMIT_BATCH` with an empty `uploadIds` array means "resume the persisted batch", not "start a new empty batch".
- If there is no persisted `active_id` or queued batch state, return an explicit error.
- The popup must surface that state to the user instead of silently pretending that resume succeeded.

## Known failure pattern

If `GetContractList` returns `520`:

1. Decode the exact bearer token being sent.
2. Compare its `tokenType`, `defaultEntityId`, and `defaultEntityTypeId` against the request headers.
3. Verify the request header `contractid` is empty.
4. Verify the active entity in session storage matches the intended sub-agent tab.

Do not start by assuming the body or endpoint is wrong. In prior incidents, the main problem was auth-token class mismatch.
