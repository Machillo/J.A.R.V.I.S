-- DINCR Labs schema: a production-SHAPED subset, applied after
-- database/baseline/v1_identity_ownership.sql on a local, disposable database.
--
-- It is not the production schema. The repository cannot rebuild production
-- from database/schema.sql + migrations (the script does not load on a fresh
-- server), so Labs keeps the tables its experiments use, with the money column
-- types verified in the repository:
--   transactions amount/original_amount NUMERIC(12,2), exchange_rate NUMERIC(12,6)
--     (production shape confirmed by gate Q0, 2026-09-28);
--   salaries/expenses amount NUMERIC(14,2), original_* and the all-or-nothing CHECK
--     exactly as 20260928110000 (explicit IS NOT NULL: a NULL CHECK passes);
--   debts, debt_payments, financial_goals, budget and recurring items NUMERIC(14,2);
--   exchange_rates NUMERIC(14,6); account_balances NUMERIC(18,2);
--   finva_email_candidates amount/original_amount NUMERIC(18,2), confidence NUMERIC(5,4).
-- Ownership is canonical: every row carries workspace_id (FK, cascade); the
-- legacy user_id is optional, as after migration 20260926130000.
-- Keep labs/limits.py in sync with the NUMERIC types here.

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS base_currency TEXT NOT NULL DEFAULT 'CRC'
    CHECK (base_currency IN ('CRC', 'USD', 'EUR', 'MXN', 'COP', 'GTQ', 'PAB', 'ARS'));
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS labs_plan TEXT NOT NULL DEFAULT 'free'
    CHECK (labs_plan IN ('free', 'basic', 'vip', 'owner_like_test'));

CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, transaction_date TEXT NOT NULL,
    description TEXT NOT NULL, amount NUMERIC(12,2) NOT NULL, transaction_type TEXT NOT NULL,
    category TEXT NOT NULL, account TEXT, source TEXT, notes TEXT,
    original_amount NUMERIC(12,2), original_currency TEXT, exchange_rate NUMERIC(12,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, financial_account_id BIGINT
);
CREATE INDEX ON transactions(workspace_id, transaction_date);

CREATE TABLE salaries (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, amount NUMERIC(14,2) NOT NULL, frequency TEXT NOT NULL DEFAULT 'monthly',
    source TEXT, received_date DATE, notes TEXT,
    original_amount NUMERIC(14,2), original_currency TEXT, exchange_rate NUMERIC(14,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    CHECK ((original_currency IS NULL AND original_amount IS NULL AND exchange_rate IS NULL)
        OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NOT NULL
            AND original_currency IN ('CRC', 'USD') AND original_amount > 0 AND exchange_rate > 0))
);
CREATE TABLE expenses (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, category TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL,
    description TEXT, expense_date DATE,
    original_amount NUMERIC(14,2), original_currency TEXT, exchange_rate NUMERIC(14,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    CHECK ((original_currency IS NULL AND original_amount IS NULL AND exchange_rate IS NULL)
        OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NOT NULL
            AND original_currency IN ('CRC', 'USD') AND original_amount > 0 AND exchange_rate > 0))
);
CREATE TABLE debts (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, name TEXT NOT NULL, debt_type TEXT NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL, remaining_amount NUMERIC(14,2) NOT NULL,
    monthly_payment NUMERIC(14,2) NOT NULL, interest_rate NUMERIC(8,4), payment_day INTEGER,
    next_payment_date DATE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE TABLE debt_payments (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, debt_id BIGINT NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    payment_type TEXT NOT NULL DEFAULT 'manual', amount NUMERIC(14,2) NOT NULL, paid_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE TABLE financial_goals (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, name TEXT NOT NULL,
    target_amount NUMERIC(14,2) NOT NULL, current_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    target_date DATE, status TEXT NOT NULL DEFAULT 'active',
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE TABLE finva_budget_items (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    category TEXT NOT NULL, monthly_limit NUMERIC(14,2) NOT NULL
);
CREATE TABLE finva_recurring_items (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, kind TEXT NOT NULL DEFAULT 'expense', day_of_month INTEGER
);
CREATE TABLE exchange_rates (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, rate_date DATE NOT NULL, currency TEXT NOT NULL,
    exchange_rate NUMERIC(14,6) NOT NULL, source TEXT,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    UNIQUE (workspace_id, rate_date, currency)
);
CREATE TABLE account_balances (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, name TEXT NOT NULL, account_type TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CRC', current_balance NUMERIC(18,2),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE
);

-- Email Monitor (shape of the review path; see backend/tests/test_mail_candidate_currency_pg.py).
CREATE TABLE finva_gmail_connections (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    legacy_user_id BIGINT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'active', provider TEXT NOT NULL DEFAULT 'labs-fixture'
);
CREATE TABLE finva_email_messages (
    id BIGSERIAL PRIMARY KEY, connection_id BIGINT NOT NULL REFERENCES finva_gmail_connections(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider_message_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE finva_email_candidates (
    id BIGSERIAL PRIMARY KEY, email_message_id BIGINT NOT NULL REFERENCES finva_email_messages(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    transaction_id BIGINT REFERENCES transactions(id), transaction_date DATE NOT NULL,
    description TEXT NOT NULL, amount NUMERIC(18,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC',
    original_amount NUMERIC(18,2), original_currency TEXT, transaction_type TEXT NOT NULL,
    category TEXT NOT NULL, bank TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'email',
    source_provider TEXT NOT NULL DEFAULT 'gmail', financial_account_id BIGINT,
    parser_name TEXT, parser_version TEXT, movement_kind TEXT, confidence NUMERIC(5,4), dedupe_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'auto_saved', 'confirmed', 'rejected', 'duplicate')),
    is_internal_transfer BOOLEAN NOT NULL DEFAULT FALSE, related_candidate_id BIGINT, resolution_reason TEXT,
    reviewed_at TIMESTAMPTZ, corrected_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE financial_input_events (
    id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id),
    event_name TEXT NOT NULL, contract_version TEXT NOT NULL,
    transaction_id BIGINT NOT NULL REFERENCES transactions(id), payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (event_name = 'transaction_confirmed' AND contract_version = 'financial-input-v1'),
    CHECK (NOT (payload ?| ARRAY['raw_payload','body','attachment_text','sender','subject']))
);
CREATE UNIQUE INDEX ON financial_input_events(transaction_id, event_name, contract_version);
CREATE TABLE notification_jobs (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES allowed_users(id), workspace_id UUID,
    title TEXT NOT NULL, body TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general',
    scheduled_at TIMESTAMPTZ NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reference_type TEXT,
    reference_id TEXT, dedupe_key TEXT, payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(workspace_id, dedupe_key)
);
