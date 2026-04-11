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

CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at_id_desc
    ON uploads (user_id, created_at DESC, id DESC);
