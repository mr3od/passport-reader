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

CREATE INDEX IF NOT EXISTS idx_broadcasts_status_created_at
    ON broadcasts (status, created_at, id);
