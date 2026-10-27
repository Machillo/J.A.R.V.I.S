-- MANUAL rollback of 20261026120000_account_statement_cut_day.sql.
-- Human decision only; never run automatically.
--
-- Precondition: nothing that converts USD expenses by statement cut is in production (roll that
-- code back first). The cut-day code itself tolerates the column's absence
-- (schema_state.columns_exist): cards show the cut day as not available.
--
-- What it does: no balance or movement changes. Only the declared cut days leave
-- `account_balances`; they are kept first in a closed snapshot table, as evidence and for a later
-- restore. Dropping a column is catalog-only: no table rewrite.
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
--   WHERE table_schema = 'public' AND table_name = 'account_balances' AND column_name = 'statement_cut_day';

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

CREATE TABLE IF NOT EXISTS public.account_statement_cut_day_rollback_snapshot (
    account_balance_id BIGINT PRIMARY KEY,  -- account_balances.id (its workspace stays on that row)
    statement_cut_day SMALLINT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.account_statement_cut_day_rollback_snapshot ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    -- Closed to the Data API, like every table the app itself does not expose.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.account_statement_cut_day_rollback_snapshot FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.account_statement_cut_day_rollback_snapshot FROM authenticated;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_attribute
               WHERE attrelid = 'public.account_balances'::regclass AND attname = 'statement_cut_day' AND NOT attisdropped) THEN
        INSERT INTO public.account_statement_cut_day_rollback_snapshot (account_balance_id, statement_cut_day)
        SELECT id, statement_cut_day FROM public.account_balances WHERE statement_cut_day IS NOT NULL
        ON CONFLICT (account_balance_id) DO UPDATE
            SET statement_cut_day = EXCLUDED.statement_cut_day, snapshot_at = NOW();
    END IF;
END $$;

ALTER TABLE public.account_balances DROP CONSTRAINT IF EXISTS account_balances_statement_cut_day_check;
ALTER TABLE public.account_balances DROP COLUMN IF EXISTS statement_cut_day;

COMMIT;
