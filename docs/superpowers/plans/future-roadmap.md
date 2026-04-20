# Future Roadmap

**Author:** kiro
**Created:** 2026-04-20

---

## Feature Distribution: Bot Commands vs Mini App

### Bot Commands (inline keyboard dashboard)
Quick, contextual actions that don't need a full UI.

| Feature | Command / Trigger |
|---|---|
| Upload passports | Send images directly |
| Live processing status | Auto (status message) |
| View individual results | Inline button per result |
| Error report (PDF) | Inline button |
| Retry failed extractions | Inline button |
| Dashboard summary | `/dashboard` — editable message with stats + buttons |
| Quick duplicate alert | Auto during upload |
| Passport version history | Inline button from result |
| Usage & quota | `/me` |
| Extension download | `/extension` |

### Telegram Mini App (WebApp)
Rich interactions that need proper UI: tables, search, filters, side-by-side
comparison, bulk actions.

| Feature | Why it needs the app |
|---|---|
| Full passport records browser | Search, filter, sort, paginate |
| Side-by-side version comparison | Two extractions next to each other |
| Confidence diff viewer | Highlight what changed between versions |
| Bulk archive / manage | Checkboxes, bulk actions |
| Detailed extraction editor | Edit fields, mark reviewed |
| Analytics dashboard | Charts, trends, per-user stats |
| Submission tracking (Masar) | Status timeline, retry from UI |
| Plan management (admin) | User list, plan changes, block/unblock |
| Export (CSV/PDF) | Filtered data export |
| Duplicate management | Merge, compare, choose best version |

---

## Feature 1: Duplicate Detection

### 1A — Exact File Duplicate (same bytes)

**Detection:** SHA-256 hash of uploaded file bytes.

**DB schema addition:**
```sql
ALTER TABLE uploads ADD COLUMN file_hash TEXT;
CREATE INDEX idx_uploads_file_hash ON uploads (file_hash);
```

**Flow:**
1. User uploads image → compute SHA-256
2. Query: `SELECT id FROM uploads WHERE user_id = ? AND file_hash = ?`
3. If match found:
   - Check if previous upload has a successful processing result
   - **If success exists:** Don't re-process. Show existing result immediately
     with note: "تم معالجة هذه الصورة مسبقاً — هذه النتيجة السابقة"
   - **If previous failed:** Re-process, but track attempt count
4. Track retry attempts per file hash:
   ```sql
   -- In processing_results or a new table
   ALTER TABLE processing_results ADD COLUMN model_used TEXT;
   ```
5. Retry limit per file hash (e.g. 3 attempts across different models):
   - Attempt 1: primary model (gemini-flash)
   - Attempt 2: fallback model (if configured)
   - Attempt 3: final attempt
   - After 3 failures: "تم محاولة معالجة هذه الصورة 3 مرات بدون نجاح.
     أرسل صورة أوضح أو صورة مختلفة للجواز."

### 1B — Same Passport, Different Photo

**Detection:** Passport number match after extraction.

**DB schema:** Already have `passport_number` in `processing_results`.

**Flow:**
1. After successful extraction, check:
   `SELECT upload_id FROM processing_results WHERE passport_number = ? AND upload_id != ?`
2. If match found → link as a "version" of the same passport
3. Store version relationship:
   ```sql
   CREATE TABLE passport_versions (
       id SERIAL PRIMARY KEY,
       passport_number TEXT NOT NULL,
       upload_id INTEGER NOT NULL REFERENCES uploads(id),
       confidence_overall REAL,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now()
   );
   CREATE INDEX idx_passport_versions_number
       ON passport_versions (passport_number);
   ```
4. User sees: "هذا الجواز تم معالجته من قبل — يمكنك مقارنة النتائج"
   with inline button to view version history

### 1C — Version Comparison

**Bot command:** Inline button "📊 مقارنة النسخ" on any result that has versions.

**Shows:**
- Number of versions
- Confidence per version
- Which fields differ
- Best version recommendation (highest confidence)

**Mini app:** Full side-by-side comparison with field-level diff highlighting.

---

## Feature 2: Dashboard Command

**Command:** `/dashboard`

**Sends an editable message with:**
```
📊 لوحة التحكم

الجوازات هذا الشهر: 45
ناجح: 40 | فشل: 5
المتبقي: 255 رفع | 260 معالجة

آخر رفع: منذ 3 دقائق
الخطة: basic

[📋 آخر النتائج]  [📊 الإحصائيات]
[🔍 بحث بالرقم]   [📁 الأرشيف]
```

**Inline buttons:**
- آخر النتائج → shows last 5 results as buttons (like queue results)
- الإحصائيات → monthly breakdown message
- بحث بالرقم → prompts user to type passport number, returns matches
- الأرشيف → shows archived records count + unarchive option

**Updates:** Message is edited when user interacts. Not auto-refreshing
(would hit rate limits). User clicks to refresh.

---

## Feature 3: Telegram Mini App

### Tech Stack
- **Frontend:** React + Tailwind (or vanilla if simpler)
- **Backend:** `passport-api` (already exists, add endpoints as needed)
- **Auth:** Telegram WebApp init data validation → map to existing user
- **Hosting:** Served from the same passport-api pod (static files)

### Screens
1. **Home / Dashboard** — stats, recent activity, quick actions
2. **Records Browser** — searchable, filterable table of all passports
3. **Record Detail** — full extraction data, image, edit fields, review
4. **Version Comparison** — side-by-side diff of same passport
5. **Submissions** — Masar submission status, retry, timeline
6. **Settings** — plan info, usage, extension download link

### API Additions Needed
- `GET /records?search=&sort=&page=` — already mostly exists
- `GET /records/:id/versions` — new
- `PATCH /records/:id/fields` — new (edit extraction)
- `GET /dashboard/stats` — new (aggregated stats)
- `POST /records/:id/retry` — new (re-extract)

---

## Feature Priority Order

| # | Feature | Effort | Impact |
|---|---|---|---|
| 1 | PostgreSQL migration | Medium | Foundation for everything |
| 2 | Exact file duplicate detection | Small | Saves quota, better UX |
| 3 | Dashboard command | Small | Quick wins, daily use |
| 4 | Same-passport version tracking | Medium | Core value for agencies |
| 5 | Version comparison (bot) | Small | Builds on #4 |
| 6 | Mini app — scaffold + auth | Medium | Platform for rich features |
| 7 | Mini app — records browser | Medium | Replaces extension for viewing |
| 8 | Mini app — version comparison | Medium | Full diff experience |
| 9 | Mini app — submission management | Medium | Replaces /masar command |
| 10 | Mini app — analytics | Low priority | Nice to have |

---

## DB Schema Additions Summary (all features)

```sql
-- Duplicate detection
ALTER TABLE uploads ADD COLUMN file_hash TEXT;
CREATE INDEX idx_uploads_file_hash ON uploads (file_hash);

-- Model tracking for retry logic
ALTER TABLE processing_results ADD COLUMN model_used TEXT;

-- Passport versioning
CREATE TABLE passport_versions (
    id SERIAL PRIMARY KEY,
    passport_number TEXT NOT NULL,
    upload_id INTEGER NOT NULL REFERENCES uploads(id),
    confidence_overall REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_passport_versions_number ON passport_versions (passport_number);
```

These additions are Postgres-native. Migration (#1) should land first.
