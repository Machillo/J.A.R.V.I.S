-- MANUAL rollback of 20260926150000_income_expense_original_currency.sql.
-- Human decision only; never run automatically.
--
-- Precondition: production no longer runs a backend that reads or writes these
-- columns (roll the income/expense currency code back first). Otherwise the
-- income, expense and movement-history endpoints fail.
--
-- What it does: `amount` is always in the base currency, so no amount, total or
-- row changes. Only the annotation of entries typed in the other currency
-- (original_amount, original_currency, exchange_rate) leaves the two tables; it
-- is kept first in a closed snapshot table, as evidence and for a later restore.
-- Dropping a column is catalog-only: no table rewrite.
--
-- How to run it (apply_migration.py refuses files outside database/migrations,
-- and docs/security/migration-safety-protocol.md §2 allows this exception):
--   1. BACKUP_VERIFIED gate open for this database (db_backup_verify.py gate);
--   2. a second person reads this file and the reason for rolling back;
--   3. psql -v ON_ERROR_STOP=1 over a direct session connection as postgres,
--      one transaction (this file's BEGIN/COMMIT).
-- Idempotent: a second run finds nothing left to snapshot or drop.
--
-- Postflight (read-only): must return zero rows.
--   SELECT table_name, column_name FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name IN ('salaries', 'expenses')
--     AND column_name IN ('original_amount', 'original_currency', 'exchange_rate');

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

CREATE TABLE IF NOT EXISTS public.income_expense_original_currency_rollback_snapshot (
    source_table TEXT NOT NULL,
    source_id BIGINT NOT NULL,
    workspace_id UUID,
    original_amount NUMERIC(14, 2) NOT NULL,
    original_currency TEXT NOT NULL,
    exchange_rate NUMERIC(14, 6) NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source_table, source_id)
);
ALTER TABLE public.income_expense_original_currency_rollback_snapshot ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    -- Closed to the Data API, like every table the app itself does not expose.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.income_expense_original_currency_rollback_snapshot FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.income_expense_original_currency_rollback_snapshot FROM authenticated;
    END IF;
END $$;

DO $$
DECLARE
    target TEXT;
BEGIN
    FOREACH target IN ARRAY ARRAY['salaries', 'expenses'] LOOP
        IF EXISTS (SELECT 1 FROM pg_attribute
                   WHERE attrelid = ('public.' || target)::regclass AND attname = 'original_currency' AND NOT attisdropped) THEN
            EXECUTE format(
                'INSERT INTO public.income_expense_original_currency_rollback_snapshot'
                '(source_table, source_id, workspace_id, original_amount, original_currency, exchange_rate) '
                'SELECT %L, id, workspace_id, original_amount, original_currency, exchange_rate FROM public.%I '
                'WHERE original_currency IS NOT NULL ON CONFLICT (source_table, source_id) DO NOTHING',
                target, target);
        END IF;
        EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', target, target || '_original_currency_check');
        EXECUTE format('ALTER TABLE public.%I DROP COLUMN IF EXISTS original_amount, '
                       'DROP COLUMN IF EXISTS original_currency, DROP COLUMN IF EXISTS exchange_rate', target);
    END LOOP;
END $$;

COMMIT;
