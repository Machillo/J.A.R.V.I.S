-- Owner legacy schema, formerly created at request time.
--
-- These statements ran on every call of the Owner modules' ensure functions
-- (email monitor, receivables and card aliases, memory, deployment monitor,
-- business center, IBKR, advisor). Request paths never create or alter schema:
-- DDL takes relation-level locks on every call, and the dedicated application role
-- (no DDL privileges) cannot run it. This migration is the exact text those
-- functions executed, captured by running them, deduplicated, in the same order.
--
-- On production every statement is a no-op except the two advisor tables, which
-- were never created there (verified on a restored backup: the schema dump is
-- identical before and after, apart from those tables). The advisor tables get an
-- optional legacy user_id (ownership is the workspace) and the history index of
-- the superseded 20260908_advisor_core.sql. Where a captured CREATE TABLE named
-- workspace_id only in a UNIQUE clause (the column used to be added by a later
-- ALTER), the column is declared. The file applies to a production-shape database
-- (verified on a restored backup) and, in CI, to the identity baseline plus
-- investment_portfolio_snapshots (backend/tests/test_owner_legacy_schema_pg.py).
-- Every statement is idempotent (IF NOT EXISTS). No row is read or changed.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres,
-- BEFORE the code of this PR is deployed (the code no longer creates these relations).
--
-- Preflight: none needed (additive, idempotent).
-- Postflight (read-only): must return zero rows.
--   SELECT t FROM unnest(ARRAY[
--     'advisor_current_strategy','advisor_strategy_history','business_movements','business_projects',
--     'card_aliases','credit_card_settings','deployment_events','email_ingested_messages',
--     'email_monitor_settings','email_parser_logs','email_statement_documents',
--     'email_transaction_candidates','exchange_rates','investment_position_snapshots','memory_items',
--     'payroll_salary_reports','receivable_entries','receivable_payments','receivables','user_preferences']) t
--   WHERE to_regclass('public.' || t) IS NULL
--   UNION ALL SELECT 'row level security off on ' || c.relname FROM pg_class c
--   WHERE c.oid IN (to_regclass('public.advisor_current_strategy'), to_regclass('public.advisor_strategy_history'))
--     AND NOT c.relrowsecurity
--   UNION ALL SELECT 'advisor user_id required on ' || table_name FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name IN ('advisor_current_strategy', 'advisor_strategy_history')
--     AND column_name = 'user_id' AND is_nullable = 'NO';
-- Rollback: none. Dropping these relations would delete data; the previous code
-- recreated them anyway, so reverting the code needs no schema change.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

-- from backend/email_monitor/service.py ensure_email_tables()
CREATE TABLE IF NOT EXISTS email_monitor_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_commit_confidence NUMERIC NOT NULL DEFAULT 0.90,
    monitored_senders TEXT[] NOT NULL DEFAULT ARRAY['bac','credomatic','popular','multimoney'],
    gmail_query TEXT NOT NULL DEFAULT '',
    last_scan_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS email_ingested_messages (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID,
    user_id BIGINT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'gmail',
    provider_message_id TEXT,
    fingerprint TEXT NOT NULL,
    sender TEXT,
    subject TEXT,
    received_at TIMESTAMPTZ,
    bank TEXT,
    status TEXT NOT NULL DEFAULT 'processed',
    raw_excerpt TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, fingerprint),
    UNIQUE(workspace_id, provider, provider_message_id)
);
ALTER TABLE email_monitor_settings ADD COLUMN IF NOT EXISTS gmail_history_id TEXT;
ALTER TABLE email_monitor_settings ADD COLUMN IF NOT EXISTS gmail_watch_expiration TIMESTAMPTZ;
ALTER TABLE email_monitor_settings ADD COLUMN IF NOT EXISTS gmail_watch_topic TEXT;
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS raw_body TEXT;
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS body_text TEXT;
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS attachment_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS parse_reason TEXT;
CREATE TABLE IF NOT EXISTS email_transaction_candidates (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID,
    user_id BIGINT NOT NULL,
    email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    transaction_id BIGINT,
    transaction_date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    transaction_type TEXT NOT NULL,
    category TEXT NOT NULL,
    account TEXT DEFAULT '',
    source TEXT NOT NULL DEFAULT 'email_monitor',
    notes TEXT DEFAULT '',
    original_amount NUMERIC,
    original_currency TEXT,
    exchange_rate NUMERIC,
    confidence NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    review_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, fingerprint)
);
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS card_last4 TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS card_owner TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS billing_cycle_start DATE;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS billing_cycle_end DATE;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS dedupe_key TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS duplicate_of BIGINT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS canonical_transaction_id BIGINT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS transaction_time TIME;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS raw_description TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS normalized_description TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS auto_commit_allowed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS personal_rule_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_email_candidates_card_cycle
ON email_transaction_candidates(workspace_id, card_last4, billing_cycle_start, billing_cycle_end);
CREATE INDEX IF NOT EXISTS idx_email_candidates_dedupe
ON email_transaction_candidates(workspace_id, transaction_date, amount, transaction_type, status);
CREATE INDEX IF NOT EXISTS idx_email_candidates_semantic_dedupe
ON email_transaction_candidates(user_id, transaction_date, amount, transaction_time, status);
CREATE TABLE IF NOT EXISTS email_statement_documents (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID,
    user_id BIGINT NOT NULL,
    email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE CASCADE,
    bank TEXT NOT NULL,
    subject TEXT,
    statement_month TEXT,
    received_at TIMESTAMPTZ,
    attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    extracted_text_excerpt TEXT,
    extracted_text TEXT,
    status TEXT NOT NULL DEFAULT 'pending_reconciliation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, email_message_id)
);
ALTER TABLE email_statement_documents ADD COLUMN IF NOT EXISTS extracted_text TEXT;
CREATE TABLE IF NOT EXISTS payroll_salary_reports (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workspace_id UUID NOT NULL,
    email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE SET NULL,
    provider_message_id TEXT,
    period_month TEXT NOT NULL,
    reported_salary NUMERIC NOT NULL,
    trans_previous_salary NUMERIC,
    previous_salary NUMERIC,
    daily_subsidy NUMERIC,
    employer_number TEXT,
    verification_code TEXT,
    source TEXT NOT NULL DEFAULT 'ccss_order_patronal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, period_month),
    UNIQUE(workspace_id, provider_message_id)
);
CREATE TABLE IF NOT EXISTS card_aliases (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID,
    user_id BIGINT NOT NULL,
    card_last4 TEXT NOT NULL,
    owner_label TEXT NOT NULL,
    relationship TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, card_last4)
);
CREATE INDEX IF NOT EXISTS idx_card_aliases_user
ON card_aliases(user_id);
CREATE TABLE IF NOT EXISTS credit_card_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL DEFAULT 'BAC tarjetas',
    cut_day INTEGER NOT NULL DEFAULT 21,
    payment_day INTEGER NOT NULL DEFAULT 5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS bank TEXT NOT NULL DEFAULT 'bac';
ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS card_last4 TEXT;
ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS owner_label TEXT;
ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_card_settings_user_bank_card
ON credit_card_settings(user_id, bank, card_last4);
CREATE TABLE IF NOT EXISTS email_parser_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    email_message_id BIGINT,
    provider_message_id TEXT,
    sender TEXT,
    subject TEXT,
    bank TEXT,
    action TEXT NOT NULL,
    result TEXT,
    reason TEXT,
    extracted_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS email_message_id BIGINT;
ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS result TEXT;
ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS extracted_payload JSONB;
ALTER TABLE email_monitor_settings ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE email_statement_documents ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE card_aliases ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS workspace_id UUID;

-- from backend/finance/intelligence.py _ensure_receivable_tables()
CREATE TABLE IF NOT EXISTS receivables (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    person_name TEXT NOT NULL,
    original_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    paid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    pending_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS source_key TEXT;
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id);
CREATE TABLE IF NOT EXISTS receivable_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL,
    source_transaction_id BIGINT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_receivables_user_status ON receivables(user_id, status);
CREATE INDEX IF NOT EXISTS idx_receivables_source_key ON receivables(workspace_id, source_key);
ALTER TABLE receivable_payments ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id);
CREATE INDEX IF NOT EXISTS idx_receivable_payments_receivable ON receivable_payments(user_id, receivable_id);
CREATE INDEX IF NOT EXISTS idx_receivables_workspace_status ON receivables(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_receivable_payments_workspace_receivable ON receivable_payments(workspace_id, receivable_id);
CREATE TABLE IF NOT EXISTS receivable_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_key TEXT,
    source_transaction_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE receivable_entries ADD COLUMN IF NOT EXISTS cycle_start DATE;
ALTER TABLE receivable_entries ADD COLUMN IF NOT EXISTS cycle_end DATE;
ALTER TABLE receivable_entries ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE receivable_entries ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id);
CREATE INDEX IF NOT EXISTS idx_receivable_entries_workspace_account ON receivable_entries(workspace_id, receivable_id, entry_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_receivable_entries_account ON receivable_entries(user_id, receivable_id, entry_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_receivable_entries_active_cycle ON receivable_entries(user_id, receivable_id, is_archived, cycle_start, cycle_end);
CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_entries_source_key ON receivable_entries(workspace_id, source_key) WHERE source_key IS NOT NULL;

-- from backend/finance/intelligence.py _ensure_card_aliases()
CREATE TABLE IF NOT EXISTS card_aliases (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    card_last4 TEXT NOT NULL,
    owner_label TEXT NOT NULL,
    relationship TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- from backend/ai/memory_service.py ensure_memory_tables()
CREATE TABLE IF NOT EXISTS memory_items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    category TEXT NOT NULL DEFAULT 'other',
    title TEXT,
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,
    source TEXT NOT NULL DEFAULT 'manual',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_items_user_active
ON memory_items(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_memory_items_category
ON memory_items(category);
CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    preference_key TEXT NOT NULL,
    preference_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, preference_key)
);
ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;
ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_memory_items_workspace_active ON memory_items(workspace_id, is_active);
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_preferences_workspace_key ON user_preferences(workspace_id, preference_key);

-- from backend/deployment_monitor/service.py ensure_deployment_table()
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

-- from backend/finance/business_center.py _ensure_tables()
CREATE TABLE IF NOT EXISTS business_projects (
  id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, workspace_id UUID, name TEXT NOT NULL,
  description TEXT, ownership_pct NUMERIC(6,2) NOT NULL DEFAULT 100,
  status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS business_movements (
  id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, workspace_id UUID,
  business_id BIGINT NOT NULL REFERENCES business_projects(id) ON DELETE CASCADE,
  movement_date DATE NOT NULL DEFAULT CURRENT_DATE, movement_type TEXT NOT NULL,
  amount NUMERIC(14,2) NOT NULL, description TEXT NOT NULL, category TEXT,
  transaction_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- from backend/integrations/ibkr_readonly.py ensure_ibkr_tables()
CREATE TABLE IF NOT EXISTS exchange_rates (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    rate_date DATE NOT NULL, currency TEXT NOT NULL,
    exchange_rate NUMERIC(14,6) NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, rate_date, currency)
);
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS snapshot_at TIMESTAMPTZ;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS cash NUMERIC(18,4) NOT NULL DEFAULT 0;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS buying_power NUMERIC(18,4) NOT NULL DEFAULT 0;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS gross_position_value NUMERIC(18,4) NOT NULL DEFAULT 0;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS accrued_cash NUMERIC(18,4) NOT NULL DEFAULT 0;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS account_id_masked TEXT;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS account_mode TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS snapshot_key TEXT;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS included_in_net_worth BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS exchange_rate_crc NUMERIC(14,6);
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS market_value_crc NUMERIC(18,2);
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS sync_method TEXT NOT NULL DEFAULT 'manual';
CREATE UNIQUE INDEX IF NOT EXISTS uq_ibkr_snapshot_key ON investment_portfolio_snapshots(workspace_id, snapshot_key) WHERE snapshot_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS investment_position_snapshots (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL,
    portfolio_snapshot_id BIGINT NOT NULL REFERENCES investment_portfolio_snapshots(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    sec_type TEXT NOT NULL,
    currency TEXT NOT NULL,
    exchange TEXT,
    position NUMERIC(24,8) NOT NULL DEFAULT 0,
    average_cost NUMERIC(18,6) NOT NULL DEFAULT 0,
    market_price NUMERIC(18,6) NOT NULL DEFAULT 0,
    market_value NUMERIC(18,4) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(18,4) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ibkr_positions_snapshot ON investment_position_snapshots(portfolio_snapshot_id);

-- from backend/advisor/core.py _ensure_strategy_tables()
CREATE TABLE IF NOT EXISTS advisor_current_strategy (
    workspace_id UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES allowed_users(id) ON DELETE CASCADE,
    advisor_version TEXT NOT NULL,
    strategy_hash TEXT NOT NULL,
    strategy JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS advisor_strategy_history (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES allowed_users(id) ON DELETE CASCADE,
    advisor_version TEXT NOT NULL,
    strategy_hash TEXT NOT NULL,
    strategy JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 20260908_advisor_core.sql declared the same tables with a required user_id; where
-- it was applied, relax it here (idempotent). That file is superseded by this one.
ALTER TABLE advisor_current_strategy ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE advisor_strategy_history ALTER COLUMN user_id DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_advisor_strategy_history_workspace_created
    ON advisor_strategy_history(workspace_id, created_at DESC);

-- Like every other table: row level security on (no policies) and no access for
-- the public API roles, which Supabase grants by default on new tables.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['advisor_current_strategy', 'advisor_strategy_history'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated', t);
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON SEQUENCE public.advisor_strategy_history_id_seq FROM anon, authenticated;
    END IF;
END $$;

COMMIT;
