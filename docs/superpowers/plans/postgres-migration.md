# PostgreSQL Migration Plan

**Branch:** `infra/postgres-migration`
**Author:** kiro
**Created:** 2026-04-20

---

## Goal

Replace SQLite with PostgreSQL for reliability, concurrent access, and
forward-compatibility with upcoming features (duplicate detection, versioning,
mini app). Migrate all existing data. Zero data loss.

---

## Current State

- SQLite at `/data/platform.sqlite3` on a PVC
- Single-writer (passport-telegram pod), readers (passport-api, passport-admin-bot)
- 9 tables, 410 uploads, 4 users
- Images stored at `/data/artifacts/uploads/` on same PVC
- All DB access goes through `passport-platform` repositories

---

## Architecture Decision

- **PostgreSQL 16** as a StatefulSet in MicroK8s (not managed cloud — overkill)
- **Single PVC** for Postgres data (`/var/lib/postgresql/data`)
- **Existing PVC** kept for artifacts (images, broadcasts) — not in Postgres
- **Connection string** via env var `DATABASE_URL` in the shared secret
- **Driver:** `psycopg` (sync, matches current `sqlite3` usage pattern)
- **Backup:** `pg_dump` CronJob → compressed file to a backup PVC, keep last 14

---

## Implementation Plan

### Phase 1: PostgreSQL Infrastructure
**Files:** `k8s/`, `Dockerfile`

- [ ] 1.1 — Create `k8s/postgres-statefulset.yaml`:
  - PostgreSQL 16 image
  - PVC for data (10Gi, expandable)
  - Resource limits (256Mi–512Mi RAM, 250m–500m CPU)
  - Readiness/liveness probes
  - Init container to set permissions
- [ ] 1.2 — Create `k8s/postgres-service.yaml`:
  - ClusterIP service `postgres.passport-reader.svc`
  - Port 5432
- [ ] 1.3 — Add `POSTGRES_PASSWORD`, `DATABASE_URL` to `passport-reader-env` secret
- [ ] 1.4 — Create `k8s/postgres-backup-cronjob.yaml`:
  - Daily `pg_dump` → `/backups/` PVC
  - Retain last 14 dumps, delete oldest
- [ ] 1.5 — Create backup PVC (`passport-reader-backups`, 5Gi)

### Phase 2: Platform Layer — Dual Driver Support
**Files:** `passport-platform/`

- [ ] 2.1 — Add `psycopg` dependency to `passport-platform`
- [ ] 2.2 — Refactor `db.py`:
  - Parse `DATABASE_URL` — if `postgresql://` use psycopg, if `sqlite:///` or
    file path use sqlite3 (backward compatible)
  - Abstract connection interface: both drivers use `conn.execute(sql, params)`
  - Handle placeholder difference: sqlite `?` → postgres `%s`
    (use a thin wrapper or query rewriter)
- [ ] 2.3 — Refactor `_upgrade_schema()`:
  - Postgres schema uses proper types (`SERIAL`, `TIMESTAMPTZ`, `BOOLEAN`,
    `JSONB` instead of `TEXT` for JSON columns)
  - Keep SQLite schema path for local dev / tests
  - Migration: `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` for both engines
- [ ] 2.4 — Update all repositories:
  - Replace `?` placeholders with engine-aware placeholders
  - Replace `sqlite3.Row` dict access with engine-neutral row access
  - Handle `RETURNING id` (Postgres) vs `lastrowid` (SQLite)
- [ ] 2.5 — Update `PlatformSettings`:
  - Add `database_url: str` field (default: `sqlite:///data/platform.sqlite3`)
  - Deprecate implicit SQLite path
- [ ] 2.6 — Update `factory.py` to pass `database_url` to `Database`

### Phase 3: Schema Creation (Postgres-native)
**Files:** `passport-platform/migrations/`

- [ ] 3.1 — Write `001_initial.sql` for Postgres:
  ```sql
  CREATE TABLE users (
      id SERIAL PRIMARY KEY,
      external_provider TEXT NOT NULL,
      external_user_id TEXT NOT NULL,
      display_name TEXT,
      plan TEXT NOT NULL DEFAULT 'free',
      status TEXT NOT NULL DEFAULT 'active',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (external_provider, external_user_id)
  );

  CREATE TABLE uploads (
      id SERIAL PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id),
      channel TEXT NOT NULL,
      external_message_id TEXT,
      external_file_id TEXT,
      filename TEXT NOT NULL,
      mime_type TEXT NOT NULL,
      source_ref TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      archived_at TIMESTAMPTZ
  );

  CREATE TABLE processing_results (
      id SERIAL PRIMARY KEY,
      upload_id INTEGER NOT NULL REFERENCES uploads(id),
      is_passport BOOLEAN NOT NULL DEFAULT FALSE,
      is_complete BOOLEAN NOT NULL DEFAULT FALSE,
      review_status TEXT NOT NULL DEFAULT 'needs_review',
      reviewed_by_user_id INTEGER,
      reviewed_at TIMESTAMPTZ,
      passport_number TEXT,
      passport_image_uri TEXT,
      confidence_overall REAL,
      extraction_result_json JSONB,
      error_code TEXT,
      completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  CREATE TABLE masar_submissions (
      id SERIAL PRIMARY KEY,
      upload_id INTEGER NOT NULL REFERENCES uploads(id),
      status TEXT,
      detail_id TEXT,
      scan_result TEXT,
      submitted_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ
  );

  CREATE TABLE usage_ledger (
      id SERIAL PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id),
      event_type TEXT NOT NULL,
      units INTEGER NOT NULL DEFAULT 1,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );

  CREATE TABLE temp_tokens (...);
  CREATE TABLE extension_sessions (...);
  CREATE TABLE broadcasts (...);

  -- Indexes for quota queries
  CREATE INDEX idx_usage_user_type_date
      ON usage_ledger (user_id, event_type, created_at);
  CREATE INDEX idx_uploads_user_created
      ON uploads (user_id, created_at);
  CREATE INDEX idx_processing_upload
      ON processing_results (upload_id);
  ```

### Phase 4: Data Migration Script
**Files:** `passport-platform/src/passport_platform/management/migrate_to_postgres.py`

- [ ] 4.1 — Write migration script:
  - Reads from SQLite file
  - Connects to Postgres via `DATABASE_URL`
  - Migrates tables in dependency order: users → uploads → processing_results
    → masar_submissions → usage_ledger → temp_tokens → extension_sessions
    → broadcasts
  - Preserves original IDs (use `OVERRIDING SYSTEM VALUE` for SERIAL columns)
  - Resets sequences after insert (`setval('table_id_seq', max(id))`)
  - Runs in a single transaction — all or nothing
  - Dry-run mode: validates without committing
  - Prints row counts before/after for verification
- [ ] 4.2 — Add CLI entry point: `uv run migrate-to-postgres`

### Phase 5: Deployment & Cutover
**Files:** `k8s/`, `deploy.sh`

- [ ] 5.1 — Deploy Postgres StatefulSet + Service
- [ ] 5.2 — Run migration script from a one-off pod/job:
  ```bash
  microk8s kubectl -n passport-reader run migrate \
    --image=<image> --rm -it --restart=Never \
    --env-from=secret/passport-reader-env \
    -- python -m passport_platform.management.migrate_to_postgres
  ```
- [ ] 5.3 — Verify: row counts, spot-check recent records, test API queries
- [ ] 5.4 — Update `passport-reader-env` secret: set `DATABASE_URL=postgresql://...`
- [ ] 5.5 — Rolling restart all deployments (telegram, api, admin-bot)
- [ ] 5.6 — Verify all services healthy, test upload flow end-to-end
- [ ] 5.7 — Keep SQLite file as backup for 7 days, then remove

### Phase 6: Cleanup

- [ ] 6.1 — Remove SQLite-specific code paths (after 1 week stable on Postgres)
- [ ] 6.2 — Update `.env.example` with `DATABASE_URL`
- [ ] 6.3 — Update README, AGENTS.md

---

## Backward Compatibility

- Phase 2 makes the platform layer work with BOTH SQLite and Postgres
- `DATABASE_URL` env var controls which engine is used
- Local dev can keep using SQLite (no Postgres required for `uv run pytest`)
- Tests continue using SQLite (fast, no setup)
- Production switches to Postgres via env var change — no code deploy needed
  after Phase 2

---

## Rollback Plan

If Postgres has issues after cutover:
1. Set `DATABASE_URL` back to SQLite path
2. Restart deployments
3. SQLite file is still on the PVC (kept for 7 days)
4. Any uploads made during Postgres period would need manual migration back
   (unlikely to be needed — we verify before removing SQLite)

---

## Storage Layout (Post-Migration)

```
PVC: passport-reader-data (existing)
├── artifacts/
│   ├── uploads/          ← passport images
│   └── broadcasts/       ← broadcast media
└── platform.sqlite3      ← kept as backup, then removed

PVC: passport-reader-postgres (new, 10Gi)
└── pgdata/               ← PostgreSQL data directory

PVC: passport-reader-backups (new, 5Gi)
└── daily/
    ├── 2026-04-21.sql.gz
    ├── 2026-04-22.sql.gz
    └── ... (last 14)
```
