CREATE INDEX IF NOT EXISTS idx_users_external_identity
    ON users (external_provider, external_user_id);

CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at
    ON uploads (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_processing_results_upload_id
    ON processing_results (upload_id);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_user_event_created_at
    ON usage_ledger (user_id, event_type, created_at);
