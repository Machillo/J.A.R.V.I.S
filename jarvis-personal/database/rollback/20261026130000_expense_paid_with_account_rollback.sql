-- MANUAL rollback of 20261026130000_expense_paid_with_account.sql.
-- Human decision only; never run automatically.
--
-- Precondition: nothing that closes USD expenses by card statement is in production (roll that
-- code back first). The "paid with" code itself tolerates the column's absence
-- (schema_state.columns_exist): expenses show "paid with" as not available.
--
-- What it does: no amount or expense changes. Only the declared links leave `expenses`; they are
-- kept first in a closed snapshot table, as evidence and for a later restore. Dropping a column
-- is catalog-only: no table rewrite.
--
-- How to run it (apply_migration.py refuses files outside database/migrations, and
-- docs/security/migration-safety-protocol.md §2 allows this exception):
--   1. BACKUP_VERIFIED gate open for this database (db_backup_verify.py gate);
--   2. a second person reads this file and the reason for rolling back;
--   3. psql -v ON_ERROR_STOP=1 over a direct session connection as postgres,
--      one transaction (this file's BEGIN/COMMIT).
-- Idempotent: a second run finds nothing left to snapshot or drop.
--
-- Postflight (read-only): must return zero rows.
--   SELECT column_name FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'expenses' AND column_name = 'financial_account_id';

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

CREATE TABLE IF NOT EXISTS public.expense_paid_with_rollback_snapshot (
    expense_id BIGINT PRIMARY KEY,  -- expenses.id (its workspace stays on that row)
    financial_account_id BIGINT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.expense_paid_with_rollback_snapshot ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    -- Closed to the Data API, like every table the app itself does not expose.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.expense_paid_with_rollback_snapshot FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.expense_paid_with_rollback_snapshot FROM authenticated;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_attribute
               WHERE attrelid = 'public.expenses'::regclass AND attname = 'financial_account_id' AND NOT attisdropped) THEN
        INSERT INTO public.expense_paid_with_rollback_snapshot (expense_id, financial_account_id)
        SELECT id, financial_account_id FROM public.expenses WHERE financial_account_id IS NOT NULL
        ON CONFLICT (expense_id) DO UPDATE
            SET financial_account_id = EXCLUDED.financial_account_id, snapshot_at = NOW();
    END IF;
END $$;

DROP INDEX IF EXISTS public.idx_expenses_financial_account;
ALTER TABLE public.expenses DROP CONSTRAINT IF EXISTS expenses_financial_account_id_fkey;
ALTER TABLE public.expenses DROP COLUMN IF EXISTS financial_account_id;

COMMIT;
