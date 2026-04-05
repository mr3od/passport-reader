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

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_users_external_identity
    ON users (external_provider, external_user_id);

CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at
    ON uploads (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at_id_desc
    ON uploads (user_id, created_at DESC, id DESC);

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at_id_desc "
            "ON uploads (user_id, created_at DESC, id DESC)"
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
        if "masar_detail_id" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN masar_detail_id TEXT")
        if "submission_entity_id" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_entity_id TEXT")
        if "submission_entity_type_id" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_entity_type_id TEXT")
        if "submission_entity_name" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_entity_name TEXT")
        if "submission_contract_id" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_contract_id TEXT")
        if "submission_contract_name" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_contract_name TEXT")
        if "submission_contract_name_ar" not in masar_columns:
            conn.execute(
                "ALTER TABLE masar_submissions ADD COLUMN submission_contract_name_ar TEXT"
            )
        if "submission_contract_name_en" not in masar_columns:
            conn.execute(
                "ALTER TABLE masar_submissions ADD COLUMN submission_contract_name_en TEXT"
            )
        if "submission_contract_number" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_contract_number TEXT")
        if "submission_contract_status" not in masar_columns:
            conn.execute(
                "ALTER TABLE masar_submissions ADD COLUMN submission_contract_status INTEGER"
            )
        if "submission_uo_subscription_status_id" not in masar_columns:
            conn.execute(
                "ALTER TABLE masar_submissions "
                "ADD COLUMN submission_uo_subscription_status_id INTEGER"
            )
        if "submission_group_id" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_group_id TEXT")
        if "submission_group_name" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_group_name TEXT")
        if "submission_group_number" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_group_number TEXT")
        if "failure_reason_code" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN failure_reason_code TEXT")
        if "failure_reason_text" not in masar_columns:
            conn.execute("ALTER TABLE masar_submissions ADD COLUMN failure_reason_text TEXT")
