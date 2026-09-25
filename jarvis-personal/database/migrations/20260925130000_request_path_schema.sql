-- Schema that request paths used to create at runtime.
--
-- Request handlers no longer run DDL (see backend/tests/test_no_runtime_ddl.py).
-- This migration versions the objects that only runtime DDL ever created, and
-- the Basic plan tables that runtime DDL never managed to create in production
-- (it ran inside read transactions that were rolled back).
--
-- Idempotent and additive: CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
-- feature rows ON CONFLICT DO NOTHING. It never drops, rewrites or deletes.
-- Objects that already exist are left exactly as they are. One transaction:
-- apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate), as
-- the role that owns the existing public tables (postgres).
-- Store billing is last: its ALTER TABLE takes an ACCESS EXCLUSIVE lock that is
-- held until COMMIT, so it is taken as late as possible, with a 1 s lock wait.
-- While the migration runs (normally well under a second), writes to accounts,
-- workspaces and financial_goals wait: apply at low traffic.
--
-- Preflight (read-only): every listed object must be present.
--   SELECT t FROM unnest(ARRAY['accounts','workspaces','financial_goals','features',
--     'plans','plan_features','notification_jobs']) t
--   WHERE to_regclass('public.' || t) IS NULL;
-- Postflight: the query at the end of this file returns zero rows.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

-- 1. Basic plan tables (same shape as superseded/20260909_finva_basic_01_07.sql, which was
--    never applied in production: do NOT apply that older file, it re-enables
--    plan features and leaves these tables open). Now closed to the Data API
--    roles. finva_goal_contributions also backs the Free goal contribution
--    write, which fails until this runs.
CREATE TABLE IF NOT EXISTS finva_budget_items (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    monthly_limit NUMERIC(14,2) NOT NULL CHECK (monthly_limit >= 0),
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, category)
);

CREATE TABLE IF NOT EXISTS finva_recurring_items (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    category TEXT NOT NULL DEFAULT 'general',
    item_type TEXT NOT NULL DEFAULT 'expense' CHECK (item_type IN ('expense','income')),
    frequency TEXT NOT NULL DEFAULT 'monthly' CHECK (frequency IN ('weekly','biweekly','monthly','quarterly','annual')),
    due_day INTEGER CHECK (due_day BETWEEN 1 AND 31),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS finva_goal_contributions (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    goal_id BIGINT NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    contribution_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finva_recurring_workspace ON finva_recurring_items(workspace_id, is_active, due_day);
CREATE INDEX IF NOT EXISTS idx_finva_goal_contributions_workspace ON finva_goal_contributions(workspace_id, contribution_date);

ALTER TABLE finva_budget_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE finva_recurring_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE finva_goal_contributions ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE finva_budget_items, finva_recurring_items, finva_goal_contributions FROM anon, authenticated;
REVOKE ALL ON SEQUENCE finva_budget_items_id_seq, finva_recurring_items_id_seq, finva_goal_contributions_id_seq FROM anon, authenticated;

-- 2. Basic feature catalogue. Existing rows and grants are never changed
--    (access also follows BUILTIN_FEATURE_MIN_PLAN in backend/auth/saas.py).
INSERT INTO features(code, description) VALUES
    ('basic_dashboard', 'Dashboard financiero completo'),
    ('guided_budget', 'Presupuesto guiado'),
    ('financial_calendar', 'Calendario financiero'),
    ('recurring_items', 'Gastos recurrentes y suscripciones'),
    ('basic_reports', 'Reportes y estadísticas')
ON CONFLICT (code) DO NOTHING;

INSERT INTO plan_features(plan_id, feature_id, enabled)
SELECT p.id, f.id, TRUE FROM plans p CROSS JOIN features f
WHERE p.code IN ('basic', 'vip')
  AND f.code IN ('basic_dashboard', 'guided_budget', 'financial_calendar', 'recurring_items', 'basic_reports')
ON CONFLICT (plan_id, feature_id) DO NOTHING;

-- 3. Notification job index the runtime DDL created (schema.sql only).
CREATE INDEX IF NOT EXISTS idx_notification_jobs_user ON notification_jobs(user_id, scheduled_at);

-- The Basic tables above hold SHARE ROW EXCLUSIVE on accounts, workspaces and
-- financial_goals until COMMIT (their foreign keys), which blocks writes to
-- those tables, including the per-request UPDATE accounts at login. Wait at most
-- 1 s for the store lock so that blocking stays short; on timeout nothing is
-- applied and the migration can be re-run.
SET LOCAL lock_timeout = '1s';

-- 4. Store billing (created in production by the old runtime DDL). Same shape
--    as production: the pending_* columns were added later by ADD COLUMN, without
--    CHECK constraints; the backend validates those values.
CREATE TABLE IF NOT EXISTS store_subscriptions (
    account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID,
    provider TEXT NOT NULL CHECK (provider IN ('apple','google','sandbox')),
    plan_code TEXT NOT NULL CHECK (plan_code IN ('basic','vip')),
    billing_period TEXT NOT NULL CHECK (billing_period IN ('monthly','annual')),
    product_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('trialing','active','grace_period','canceled','expired','revoked')),
    provider_subscription_id TEXT,
    original_transaction_id TEXT,
    trial_ends_at TIMESTAMPTZ,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE store_subscriptions ADD COLUMN IF NOT EXISTS pending_plan_code TEXT;
ALTER TABLE store_subscriptions ADD COLUMN IF NOT EXISTS pending_billing_period TEXT;
ALTER TABLE store_subscriptions ADD COLUMN IF NOT EXISTS pending_product_id TEXT;
ALTER TABLE store_subscriptions ADD COLUMN IF NOT EXISTS pending_effective_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS store_subscription_events (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    provider_event_id TEXT,
    plan_code TEXT,
    billing_period TEXT,
    effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_store_event_provider_id
    ON store_subscription_events(provider, provider_event_id) WHERE provider_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_store_subscription_status
    ON store_subscriptions(status, current_period_end);

ALTER TABLE store_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE store_subscription_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE store_subscriptions, store_subscription_events FROM anon, authenticated;
REVOKE ALL ON SEQUENCE store_subscription_events_id_seq FROM anon, authenticated;

COMMIT;

-- Operator note: apply after the code that stops running runtime DDL is live on
-- every instance (see the PR's rollout order). If the 5 s lock_timeout aborts
-- this migration, nothing was applied and it can be re-run.
--
-- Postflight (read-only): every row returned is a failure.
-- WITH t(name) AS (VALUES ('store_subscriptions'),('store_subscription_events'),
--        ('finva_budget_items'),('finva_recurring_items'),('finva_goal_contributions')),
--      s(name) AS (VALUES ('store_subscription_events_id_seq'),('finva_budget_items_id_seq'),
--        ('finva_recurring_items_id_seq'),('finva_goal_contributions_id_seq')),
--      r(role) AS (VALUES ('anon'),('authenticated'))
-- SELECT 'missing or no RLS: ' || name FROM t
--  WHERE to_regclass('public.' || name) IS NULL
--     OR NOT (SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass('public.' || name))
-- UNION ALL
-- SELECT 'owner differs: ' || name FROM t
--  WHERE (SELECT relowner FROM pg_class WHERE oid = to_regclass('public.' || name))
--     <> (SELECT relowner FROM pg_class WHERE oid = 'public.accounts'::regclass)
-- UNION ALL
-- SELECT 'open table: ' || role || ' ' || name FROM t, r
--  WHERE to_regclass('public.' || name) IS NOT NULL AND has_table_privilege(role, to_regclass('public.' || name),
--        'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
-- UNION ALL
-- SELECT 'open sequence: ' || role || ' ' || name FROM s, r
--  WHERE to_regclass('public.' || name) IS NOT NULL AND has_sequence_privilege(role, to_regclass('public.' || name), 'USAGE,SELECT,UPDATE')
-- UNION ALL
-- SELECT 'Free has a Basic feature: ' || f.code FROM plan_features pf JOIN plans p ON p.id = pf.plan_id
--   JOIN features f ON f.id = pf.feature_id
--  WHERE p.code = 'free' AND f.code IN ('basic_dashboard','guided_budget','financial_calendar','recurring_items','basic_reports')
-- UNION ALL
-- SELECT 'missing feature: ' || code FROM (VALUES ('basic_dashboard'),('guided_budget'),('financial_calendar'),
--        ('recurring_items'),('basic_reports')) c(code)
--  WHERE NOT EXISTS (SELECT 1 FROM features f WHERE f.code = c.code)
-- UNION ALL
-- SELECT 'missing index: ' || name FROM (VALUES ('idx_finva_recurring_workspace'),('idx_finva_goal_contributions_workspace'),
--        ('idx_notification_jobs_user'),('uq_store_event_provider_id'),('idx_store_subscription_status')) i(name)
--  WHERE to_regclass('public.' || name) IS NULL;
