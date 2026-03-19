---
name: web-intel
description: Analyze an exported browser session (HAR file + storage state JSON) to plan web scraping or data-entry automation. Use when the user provides a .har file and/or state.json and wants a strategy for automating interactions with a site.
license: MIT
---

Ask the user for their `.har` and `state.json` paths if not provided, then read both files.

Ask only two questions — everything else comes from the files:
1. Goal: scraping, data entry, or both?
2. Anything the files can't tell you? (optional)

Then propose ranked strategies. For each: what approach, what session data it uses, key steps, pros, cons, best when.

## How to export

**HAR** — DevTools → Network → right-click any request → *Save all as HAR with content*

**state.json** — run in the DevTools console:
```js
copy(JSON.stringify({cookies:document.cookie.split(';').map(c=>({name:c.split('=')[0].trim(),value:c.split('=').slice(1).join('=')})),origins:[{origin:location.origin,localStorage:Object.keys(localStorage).map(k=>({name:k,value:localStorage.getItem(k)}))}]}))
```
Paste clipboard into `state.json`.

## Gotchas

- **`state.json` beats HAR for auth.** HAR headers are mid-session snapshots. `state.json` has the complete final cookies and localStorage. Always prefer it.

- **localStorage tokens won't appear in HAR request headers.** Sites inject them via JS at request time. A key like `trustedDeviceToken` in `state.json → origins[].localStorage` is why replayed requests get 406 even when cookies look right.

- **CSRF tokens can't be replayed.** Must be fetched fresh at runtime. Flag any POST that sends one.

- **HAR only covers pages the user visited.** Pagination and bulk endpoints are unknown unless they appear in entries — raise this as a gap.

- **Check token age.** `entries[0].startedDateTime` tells you when the session was recorded. Decode the JWT middle segment (base64) to read `exp`. Flag if stale.

- **Data-entry goal → ignore the data source.** Focus on the target form only.
