from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from passport_platform.config import PlatformSettings

SCHEMA_SQL = """
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
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS processing_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL UNIQUE,
    is_passport INTEGER NOT NULL,
    has_face INTEGER NOT NULL,
    is_complete INTEGER NOT NULL,
    passport_number TEXT,
    passport_image_uri TEXT,
    face_crop_uri TEXT,
    core_result_json TEXT,
    error_code TEXT,
    completed_at TEXT NOT NULL,
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
    expires_at TEXT NOT NULL,
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
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_users_external_identity
    ON users (external_provider, external_user_id);

CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at
    ON uploads (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_processing_results_upload_id
    ON processing_results (upload_id);

CREATE INDEX IF NOT EXISTS idx_temp_tokens_user_created_at
    ON temp_tokens (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_extension_sessions_user_created_at
    ON extension_sessions (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_user_event_created_at
    ON usage_ledger (user_id, event_type, created_at);
"""


class Database:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> Database:
        return cls(settings.db_path)

    def initialize(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SCHEMA_SQL)
            self._upgrade_schema(conn)
            conn.executescript(INDEX_SQL)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        with self.connect() as conn:
            try:
                if immediate:
                    conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _upgrade_schema(conn: sqlite3.Connection) -> None:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(processing_results)").fetchall()
        }
        if "passport_image_uri" not in columns:
            conn.execute("ALTER TABLE processing_results ADD COLUMN passport_image_uri TEXT")
        if "face_crop_uri" not in columns:
            conn.execute("ALTER TABLE processing_results ADD COLUMN face_crop_uri TEXT")
        if "core_result_json" not in columns:
            conn.execute("ALTER TABLE processing_results ADD COLUMN core_result_json TEXT")
        if "masar_status" not in columns:
            conn.execute("ALTER TABLE processing_results ADD COLUMN masar_status TEXT")
        if "masar_mutamer_id" not in columns:
            conn.execute("ALTER TABLE processing_results ADD COLUMN masar_mutamer_id TEXT")
        if "masar_scan_result_json" not in columns:
            conn.execute("ALTER TABLE processing_results ADD COLUMN masar_scan_result_json TEXT")
