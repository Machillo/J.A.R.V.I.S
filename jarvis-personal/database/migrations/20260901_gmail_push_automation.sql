-- Gmail Push / Pub/Sub state for automatic financial email ingestion.
ALTER TABLE email_monitor_settings
    ADD COLUMN IF NOT EXISTS gmail_history_id TEXT,
    ADD COLUMN IF NOT EXISTS gmail_watch_expiration TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS gmail_watch_topic TEXT;
