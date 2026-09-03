CREATE TABLE IF NOT EXISTS deployment_events (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    service_name TEXT,
    event_type TEXT,
    status TEXT NOT NULL,
    commit_sha TEXT,
    summary TEXT,
    detail TEXT,
    log_url TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(provider, external_id)
);

CREATE INDEX IF NOT EXISTS idx_deployment_events_created ON deployment_events(created_at DESC);
