---
name: har-api-doc
description: Reverse-engineer an undocumented API from a HAR file and optional state.json. Use when the user wants to document exact request/response shapes, ID flows between steps, and non-obvious field names for a specific browser workflow.
license: MIT
---

Ask for the `.har` and `state.json` paths and the workflow name (e.g. "add user", "checkout") if not provided, then read both files.

Ask only one question beyond that — anything the files can't answer? (optional)

---

For each request in the workflow, output one block in this exact format:

```
ENDPOINT:   <METHOD> <full path>
PURPOSE:    <one-line description>
HEADERS (custom only, skip standard browser headers):
  <name>: <value>
REQUEST BODY:
  <full JSON, or multipart field list>
RESPONSE BODY:
  <full JSON, or key fields if large>
NOTES:
  <field names, typos, IDs reused in later steps — anything non-obvious>
```

Order blocks chronologically as they appear in the HAR.

---

From `state.json` extract separately:
- Stored tokens, session IDs, entity IDs, contract IDs
- Any structured objects (e.g. current user, active contract)
- Note what is **absent** (e.g. "entity ID not in storage — only seen in request headers")

---

End with a **SUMMARY** section:

1. Ordered call sequence for the workflow
2. ID chain — every ID that flows from one response into a later request body
3. Gotchas — field name typos, envelope shapes, fields sent twice with different names, cases where the server rewrites an ID before returning it

---

## Rules

- Show **exact** field names and values. Do not paraphrase or rename anything.
- Mask only session tokens and cookies with `[REDACTED]`.
- If a field name looks like a typo (e.g. `muamer`, `Inforamtion`, `martial`), flag it explicitly — the implementation must match.
- If the same data is sent under two different keys, show both.
- If a response envelope wraps data (e.g. `{ response: { data: { ... } } }`), document the full path to the payload.

## Gotchas

- **Response envelopes hide the real payload.** Always document the full key path, not just the inner object. Implementations that unwrap one level too few will silently get the wrong data.

- **IDs get rewritten by the server.** An ID sent in step 2 may come back with a different value in step 3. Always diff send vs receive and flag mismatches.

- **Multipart requests must not set Content-Type manually.** The browser sets it with the boundary. Flag every multipart endpoint so the implementer knows to omit the header.

- **Fields sent twice.** Some APIs accept the same value under two keys (e.g. `phone.phoneNumber` and `mobileNo`). Both must be sent — sending only one may silently fail.

- **state.json vs HAR for auth.** `state.json` has the final storage state. HAR headers are mid-session. Always check both; note which source each credential came from.
