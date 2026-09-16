BEGIN;

CREATE TABLE IF NOT EXISTS legal_acceptances (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    terms_version TEXT NOT NULL,
    privacy_version TEXT NOT NULL,
    terms_accepted_at TIMESTAMPTZ NOT NULL,
    privacy_accepted_at TIMESTAMPTZ NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id,terms_version,privacy_version)
);

CREATE INDEX IF NOT EXISTS idx_legal_acceptances_account
    ON legal_acceptances(account_id,created_at DESC);

ALTER TABLE legal_acceptances ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE legal_acceptances FROM anon, authenticated;

COMMIT;
