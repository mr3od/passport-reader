from __future__ import annotations

import contextlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from passport_platform.config import PlatformSettings

# ── SQL placeholder conversion ────────────────────────────────────────────────

_QMARK_RE = re.compile(r"\?")


def _sqlite_to_pg(sql: str) -> str:
    """Convert ``?`` placeholders to ``%s`` for psycopg."""
    counter = 0

    def _replace(_: re.Match) -> str:  # type: ignore[type-arg]
        nonlocal counter
        counter += 1
        return "%s"

    return _QMARK_RE.sub(_replace, sql)


# ── Cursor / Row wrappers ────────────────────────────────────────────────────


class _PgRow:
    """Dict-like row wrapper for psycopg cursor results."""

    __slots__ = ("_data",)

    def __init__(self, keys: list[str], values: tuple) -> None:  # type: ignore[type-arg]
        self._data = dict(zip(keys, values, strict=False))

    def __getitem__(self, key: str | int) -> object:
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data[key]

    def keys(self) -> list[str]:
        return list(self._data.keys())


class _PgCursorResult:
    """Wraps a psycopg cursor to look like sqlite3.Cursor."""

    __slots__ = ("_cursor", "lastrowid")

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self.lastrowid: int | None = None

    def fetchone(self) -> _PgRow | None:
        row = self._cursor.fetchone()  # type: ignore[union-attr]
        if row is None:
            return None
        cols = [d.name for d in self._cursor.description]  # type: ignore[union-attr]
        return _PgRow(cols, row)

    def fetchall(self) -> list[_PgRow]:
        rows = self._cursor.fetchall()  # type: ignore[union-attr]
        if not rows:
            return []
        cols = [d.name for d in self._cursor.description]  # type: ignore[union-attr]
        return [_PgRow(cols, r) for r in rows]


class _PgConnectionWrapper:
    """Wraps a psycopg connection to match the sqlite3.Connection interface
    used by repositories: ``conn.execute(sql, params)``."""

    __slots__ = ("_conn",)

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()) -> _PgCursorResult:  # type: ignore[type-arg, assignment]
        pg_sql = _sqlite_to_pg(sql)
        # Auto-append RETURNING id for INSERT so lastrowid works.
        stripped = pg_sql.strip().rstrip(";").strip()
        needs_returning = (
            stripped.upper().startswith("INSERT") and "RETURNING" not in stripped.upper()
        )
        if needs_returning:
            pg_sql = stripped + " RETURNING id"
        cursor = self._conn.execute(pg_sql, params)  # type: ignore[union-attr]
        result = _PgCursorResult(cursor)
        if needs_returning and cursor.description:
            try:
                row = cursor.fetchone()
                if row is not None:
                    result.lastrowid = row[0]
            except Exception:
                pass
        return result

    def executescript(self, sql: str) -> None:
        self._conn.execute(sql)  # type: ignore[union-attr]

    def commit(self) -> None:
        self._conn.commit()  # type: ignore[union-attr]

    def rollback(self) -> None:
        self._conn.rollback()  # type: ignore[union-attr]

    def close(self) -> None:
        self._conn.close()  # type: ignore[union-attr]


# ── Schema SQL ────────────────────────────────────────────────────────────────

SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_provider TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    display_name TEXT,
    plan TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (external_provider, external_user_id)
);

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    external_message_id TEXT,
    external_file_id TEXT,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    archived_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS processing_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL UNIQUE,
    is_passport INTEGER NOT NULL,
    is_complete INTEGER NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'auto',
    reviewed_by_user_id INTEGER,
    reviewed_at TEXT,
    passport_number TEXT,
    passport_image_uri TEXT,
    confidence_overall REAL,
    extraction_result_json TEXT,
    error_code TEXT,
    completed_at TEXT NOT NULL,
    FOREIGN KEY (upload_id) REFERENCES uploads(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS masar_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    mutamer_id TEXT,
    scan_result_json TEXT,
    masar_detail_id TEXT,
    submission_entity_id TEXT,
    submission_entity_type_id TEXT,
    submission_entity_name TEXT,
    submission_contract_id TEXT,
    submission_contract_name TEXT,
    submission_contract_name_ar TEXT,
    submission_contract_name_en TEXT,
    submission_contract_number TEXT,
    submission_contract_status INTEGER,
    submission_uo_subscription_status_id INTEGER,
    submission_group_id TEXT,
    submission_group_name TEXT,
    submission_group_number TEXT,
    failure_reason_code TEXT,
    failure_reason_text TEXT,
    submitted_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (upload_id) REFERENCES uploads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS temp_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS extension_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token_hash TEXT NOT NULL UNIQUE,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS usage_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    upload_id INTEGER,
    event_type TEXT NOT NULL,
    units INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (upload_id) REFERENCES uploads(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by_external_user_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    text_body TEXT,
    caption TEXT,
    artifact_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    total_targets INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
"""

PG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    external_provider TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    display_name TEXT,
    plan TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (external_provider, external_user_id)
);

CREATE TABLE IF NOT EXISTS uploads (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    external_message_id TEXT,
    external_file_id TEXT,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS processing_results (
    id SERIAL PRIMARY KEY,
    upload_id INTEGER NOT NULL UNIQUE REFERENCES uploads(id) ON DELETE CASCADE,
    is_passport BOOLEAN NOT NULL,
    is_complete BOOLEAN NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'auto',
    reviewed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TEXT,
    passport_number TEXT,
    passport_image_uri TEXT,
    confidence_overall REAL,
    extraction_result_json TEXT,
    error_code TEXT,
    completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS masar_submissions (
    id SERIAL PRIMARY KEY,
    upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    mutamer_id TEXT,
    scan_result_json TEXT,
    masar_detail_id TEXT,
    submission_entity_id TEXT,
    submission_entity_type_id TEXT,
    submission_entity_name TEXT,
    submission_contract_id TEXT,
    submission_contract_name TEXT,
    submission_contract_name_ar TEXT,
    submission_contract_name_en TEXT,
    submission_contract_number TEXT,
    submission_contract_status INTEGER,
    submission_uo_subscription_status_id INTEGER,
    submission_group_id TEXT,
    submission_group_name TEXT,
    submission_group_number TEXT,
    failure_reason_code TEXT,
    failure_reason_text TEXT,
    submitted_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS temp_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extension_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token_hash TEXT NOT NULL UNIQUE,
    revoked_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_ledger (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    upload_id INTEGER REFERENCES uploads(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    units INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id SERIAL PRIMARY KEY,
    created_by_external_user_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    text_body TEXT,
    caption TEXT,
    artifact_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    total_targets INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_users_external_identity
    ON users (external_provider, external_user_id);

CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at
    ON uploads (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at_id_desc
    ON uploads (user_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_uploads_user_archived_at_id_desc
    ON uploads (user_id, archived_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_processing_results_upload_id
    ON processing_results (upload_id);

CREATE INDEX IF NOT EXISTS idx_processing_results_confidence
    ON processing_results (confidence_overall);

CREATE INDEX IF NOT EXISTS idx_processing_results_review_status
    ON processing_results (review_status);

CREATE INDEX IF NOT EXISTS idx_masar_submissions_upload_id_id
    ON masar_submissions (upload_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_masar_submissions_status
    ON masar_submissions (status);

CREATE INDEX IF NOT EXISTS idx_temp_tokens_user_created_at
    ON temp_tokens (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_extension_sessions_user_created_at
    ON extension_sessions (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_user_event_created_at
    ON usage_ledger (user_id, event_type, created_at);

CREATE INDEX IF NOT EXISTS idx_broadcasts_status_created_at
    ON broadcasts (status, created_at, id);
"""


# ── Database class ────────────────────────────────────────────────────────────


class Database:
    """Dual-engine database: SQLite (file path) or PostgreSQL (URL)."""

    def __init__(self, dsn: Path | str) -> None:
        dsn_str = str(dsn)
        self._is_pg = dsn_str.startswith("postgresql://") or dsn_str.startswith("postgres://")
        self._dsn = dsn_str
        if not self._is_pg:
            self._db_path = Path(dsn_str)

    @property
    def is_postgres(self) -> bool:
        return self._is_pg

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> Database:
        if settings.database_url:
            return cls(settings.database_url)
        return cls(settings.db_path)

    def initialize(self) -> None:
        if self._is_pg:
            self._initialize_pg()
        else:
            self._initialize_sqlite()

    def _initialize_sqlite(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SQLITE_SCHEMA_SQL)
            self._upgrade_schema_sqlite(conn)
            conn.executescript(INDEX_SQL)

    def _initialize_pg(self) -> None:
        with self.transaction() as conn:
            conn.executescript(PG_SCHEMA_SQL)
            conn.executescript(INDEX_SQL)

    @contextmanager
    def connect(self) -> Iterator:
        if self._is_pg:
            yield from self._connect_pg()
        else:
            yield from self._connect_sqlite()

    def _connect_sqlite(self) -> Iterator[sqlite3.Connection]:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _connect_pg(self) -> Iterator[_PgConnectionWrapper]:
        import psycopg

        conn = psycopg.connect(self._dsn, autocommit=True)
        wrapper = _PgConnectionWrapper(conn)
        try:
            yield wrapper
        finally:
            wrapper.close()

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator:
        if self._is_pg:
            yield from self._transaction_pg()
        else:
            yield from self._transaction_sqlite(immediate=immediate)

    def _transaction_sqlite(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        ctx = self._connect_sqlite()
        conn = next(ctx)
        try:
            if immediate:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            with contextlib.suppress(StopIteration):
                next(ctx)

    def _transaction_pg(self) -> Iterator[_PgConnectionWrapper]:
        import psycopg

        conn = psycopg.connect(self._dsn, autocommit=False)
        wrapper = _PgConnectionWrapper(conn)
        try:
            yield wrapper
            wrapper.commit()
        except Exception:
            wrapper.rollback()
            raise
        finally:
            wrapper.close()

    # ── SQLite schema upgrades (backward compat) ──────────────────────────

    @staticmethod
    def _upgrade_schema_sqlite(conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at_id_desc "
            "ON uploads (user_id, created_at DESC, id DESC)"
        )
        upload_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(uploads)").fetchall()
        }
        if "archived_at" not in upload_columns:
            conn.execute("ALTER TABLE uploads ADD COLUMN archived_at TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uploads_user_archived_at_id_desc "
            "ON uploads (user_id, archived_at DESC, id DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by_external_user_id TEXT NOT NULL,
                content_type TEXT NOT NULL,
                text_body TEXT,
                caption TEXT,
                artifact_path TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                total_targets INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_broadcasts_status_created_at "
            "ON broadcasts (status, created_at, id)"
        )
        masar_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(masar_submissions)").fetchall()
        }
        new_masar_cols = [
            "masar_detail_id",
            "submission_entity_id",
            "submission_entity_type_id",
            "submission_entity_name",
            "submission_contract_id",
            "submission_contract_name",
            "submission_contract_name_ar",
            "submission_contract_name_en",
            "submission_contract_number",
            "submission_contract_status",
            "submission_uo_subscription_status_id",
            "submission_group_id",
            "submission_group_name",
            "submission_group_number",
            "failure_reason_code",
            "failure_reason_text",
        ]
        for col in new_masar_cols:
            if col not in masar_columns:
                col_type = (
                    "INTEGER"
                    if col in ("submission_contract_status", "submission_uo_subscription_status_id")
                    else "TEXT"
                )
                conn.execute(f"ALTER TABLE masar_submissions ADD COLUMN {col} {col_type}")
