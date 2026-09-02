BEGIN;

CREATE TABLE IF NOT EXISTS email_financial_accounts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workspace_id UUID NOT NULL,
    account_key TEXT NOT NULL,
    institution TEXT NOT NULL,
    account_last4 TEXT NOT NULL CHECK (account_last4 ~ '^\\d{4}$'),
    ownership TEXT NOT NULL CHECK (ownership IN ('own', 'counterparty')),
    display_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, account_key),
    UNIQUE (workspace_id, institution, account_last4)
);

CREATE TABLE IF NOT EXISTS email_classification_rules (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workspace_id UUID NOT NULL,
    name TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    concept_pattern TEXT NOT NULL DEFAULT '',
    match_mode TEXT NOT NULL DEFAULT 'contains' CHECK (match_mode IN ('exact', 'contains', 'regex')),
    direction TEXT CHECK (direction IN ('in', 'out', 'payment', 'unknown')),
    origin_account_key TEXT,
    destination_account_key TEXT,
    action TEXT NOT NULL CHECK (action IN ('classify', 'ignore', 'review')),
    output_description TEXT,
    transaction_type TEXT,
    category TEXT,
    allow_auto_commit BOOLEAN NOT NULL DEFAULT FALSE,
    review_reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, name)
);

ALTER TABLE email_transaction_candidates
    ADD COLUMN IF NOT EXISTS auto_commit_allowed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE email_transaction_candidates
    ADD COLUMN IF NOT EXISTS personal_rule_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_email_financial_accounts_workspace
    ON email_financial_accounts(workspace_id, active, account_last4);

CREATE INDEX IF NOT EXISTS idx_email_classification_rules_workspace
    ON email_classification_rules(workspace_id, active, priority DESC);

COMMIT;
