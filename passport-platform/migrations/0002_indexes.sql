CREATE INDEX IF NOT EXISTS idx_users_external_identity
    ON users (external_provider, external_user_id);

CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at
    ON uploads (user_id, created_at);

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
