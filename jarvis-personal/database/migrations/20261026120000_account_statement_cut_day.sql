-- A credit card's statement cut day (día de corte), declared by the user.
--
-- USD expenses paid with a card stay in dollars until that card's statement cut, when the user
-- converts them with one exchange rate (later changes). This migration only lets a card carry
-- its cut day: `account_balances.statement_cut_day` (1–31; a month shorter than the day cuts on
-- its last day). NULL = not declared: DINCR never assumes a cut day, and never uses the Owner's
-- legacy card settings for anyone.
--
-- Additive and idempotent: ADD COLUMN IF NOT EXISTS, nullable, no default (a catalog-only
-- change: no table rewrite, no backfill) and a CHECK added NOT VALID then validated (every
-- existing row is NULL). It never drops, updates or deletes. dincr_app's table-level SELECT,
-- INSERT, UPDATE on account_balances (20260926150000) already cover the column: no grant here.
-- One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
-- The backend reads and writes the column only once it exists (schema_state.columns_exist), so
-- the code may deploy before this is applied; until then the cut day is "not available yet".
--
-- Preflight (read-only): must return zero rows. A missing table, or the column already present
-- (added by hand: IF NOT EXISTS would keep its type and data), means stop and investigate.
--   SELECT 'missing table' WHERE to_regclass('public.account_balances') IS NULL
--   UNION ALL
--   SELECT 'column already exists: ' || data_type FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'account_balances' AND column_name = 'statement_cut_day';
-- Postflight (read-only, run after COMMIT as its own query): must return zero rows — the column
-- exists as a nullable smallint with no default, its CHECK is validated, and no row was set.
--   SELECT 'column missing or wrong type' AS problem
--   WHERE NOT EXISTS (
--       SELECT 1 FROM information_schema.columns
--       WHERE table_schema = 'public' AND table_name = 'account_balances' AND column_name = 'statement_cut_day'
--         AND data_type = 'smallint' AND is_nullable = 'YES' AND column_default IS NULL
--   )
--   UNION ALL
--   SELECT 'constraint missing or not validated'
--   WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'account_balances_statement_cut_day_check'
--                     AND conrelid = 'public.account_balances'::regclass AND convalidated)
--   UNION ALL
--   SELECT 'existing rows were set: ' || count(*) FROM public.account_balances WHERE statement_cut_day IS NOT NULL
--   HAVING count(*) > 0;
-- Rollback (manual, human decision): database/rollback/20261026120000_account_statement_cut_day_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE public.account_balances ADD COLUMN IF NOT EXISTS statement_cut_day SMALLINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'account_balances_statement_cut_day_check' AND conrelid = 'public.account_balances'::regclass
    ) THEN
        ALTER TABLE public.account_balances ADD CONSTRAINT account_balances_statement_cut_day_check
            CHECK (statement_cut_day IS NULL OR statement_cut_day BETWEEN 1 AND 31) NOT VALID;
    END IF;
    ALTER TABLE public.account_balances VALIDATE CONSTRAINT account_balances_statement_cut_day_check;
END $$;

COMMENT ON COLUMN public.account_balances.statement_cut_day IS
    'Credit card statement cut day declared by the user (1-31; a shorter month cuts on its last day). '
    'NULL: not declared, never assumed.';

COMMIT;
