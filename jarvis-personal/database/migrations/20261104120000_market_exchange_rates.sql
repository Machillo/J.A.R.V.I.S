-- Daily public exchange rates (Banco Central de Costa Rica), read by the server once a day.
--
-- `exchange_rates` holds what each workspace typed. This table holds the published figure, which is
-- the same for everyone: no account, no workspace and nothing about a user. Dollar expenses use it
-- for their estimate (the purchase day's rate) and for their conversion (the rate of the close).
--
-- Additive and idempotent: one new empty table. It never touches an existing table or row.
-- One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
-- PRE-MERGE GATE: apply before the cron starts; until then the code reads "no rates" and does nothing.
--
-- Preflight (read-only): must return zero rows.
--   SELECT 'table already exists' WHERE to_regclass('public.market_exchange_rates') IS NOT NULL;
-- Postflight (read-only, run after COMMIT as its own query): must return zero rows.
--   SELECT 'table missing' WHERE to_regclass('public.market_exchange_rates') IS NULL
--   UNION ALL
--   SELECT 'rls off' FROM pg_class WHERE oid = to_regclass('public.market_exchange_rates') AND NOT relrowsecurity;
-- Rollback (manual, human decision): database/rollback/20261104120000_market_exchange_rates_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

CREATE TABLE IF NOT EXISTS public.market_exchange_rates (
    rate_date DATE NOT NULL,
    currency TEXT NOT NULL,
    rate_type TEXT NOT NULL,
    rate NUMERIC(14, 6) NOT NULL CHECK (rate > 0),
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rate_date, currency, rate_type)
);

COMMENT ON TABLE public.market_exchange_rates IS
    'Published daily rates (no user data). See backend/integrations/bccr_rates.py.';

ALTER TABLE public.market_exchange_rates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.market_exchange_rates FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.market_exchange_rates TO dincr_app;

-- Re-created on every run, so a re-run leaves exactly this policy.
DROP POLICY IF EXISTS dincr_app_access ON public.market_exchange_rates;
CREATE POLICY dincr_app_access ON public.market_exchange_rates AS PERMISSIVE FOR ALL TO dincr_app
    USING (true) WITH CHECK (true);

COMMIT;
