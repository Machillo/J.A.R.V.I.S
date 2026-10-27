-- A manual expense's "paid with" account or card.
--
-- USD expenses paid with a card stay in dollars until that card's statement cut (20261026120000),
-- so a manual expense needs to say which card or account paid it. This migration only adds the
-- link: `expenses.financial_account_id` → `account_balances(id)`, ON DELETE SET NULL (the same
-- link `transactions` has since 20260904). NULL = not told: an expense without it is still an
-- expense, and DINCR never infers the card. The backend checks the account belongs to the same
-- workspace before writing it; the FK alone does not.
--
-- Additive and idempotent: ADD COLUMN IF NOT EXISTS, nullable, no default (catalog-only: no table
-- rewrite, no backfill), the FK added NOT VALID then validated (every existing row is NULL) and a
-- partial index (only linked rows). It never drops, updates or deletes. dincr_app's table-level
-- SELECT, INSERT, UPDATE, DELETE on expenses (20260926150000) already cover the column: no grant.
-- One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
-- The backend reads and writes the column only once it exists (schema_state.columns_exist), so
-- the code may deploy before this is applied; until then "paid with" is "not available yet".
--
-- Preflight (read-only): must return zero rows. A missing table, or the column already present
-- (added by hand: IF NOT EXISTS would keep its type and data), means stop and investigate.
--   SELECT 'missing table: ' || t FROM unnest(ARRAY['public.expenses', 'public.account_balances']) AS t
--   WHERE to_regclass(t) IS NULL
--   UNION ALL
--   SELECT 'column already exists: ' || data_type FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'expenses' AND column_name = 'financial_account_id';
-- Postflight (read-only, run after COMMIT as its own query): must return zero rows — the column
-- exists as a nullable bigint with no default, its FK is validated, the index exists, and no row
-- was linked.
--   SELECT 'column missing or wrong type' AS problem
--   WHERE NOT EXISTS (
--       SELECT 1 FROM information_schema.columns
--       WHERE table_schema = 'public' AND table_name = 'expenses' AND column_name = 'financial_account_id'
--         AND data_type = 'bigint' AND is_nullable = 'YES' AND column_default IS NULL
--   )
--   UNION ALL
--   SELECT 'foreign key missing or not validated'
--   WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'expenses_financial_account_id_fkey'
--                     AND conrelid = 'public.expenses'::regclass AND contype = 'f' AND convalidated
--                     AND confrelid = 'public.account_balances'::regclass AND confdeltype = 'n')
--   UNION ALL
--   SELECT 'index missing' WHERE to_regclass('public.idx_expenses_financial_account') IS NULL
--   UNION ALL
--   SELECT 'existing rows were linked: ' || count(*) FROM public.expenses WHERE financial_account_id IS NOT NULL
--   HAVING count(*) > 0;
-- Rollback (manual, human decision): database/rollback/20261026130000_expense_paid_with_account_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE public.expenses ADD COLUMN IF NOT EXISTS financial_account_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'expenses_financial_account_id_fkey' AND conrelid = 'public.expenses'::regclass
    ) THEN
        ALTER TABLE public.expenses ADD CONSTRAINT expenses_financial_account_id_fkey
            FOREIGN KEY (financial_account_id) REFERENCES public.account_balances(id) ON DELETE SET NULL NOT VALID;
    END IF;
    ALTER TABLE public.expenses VALIDATE CONSTRAINT expenses_financial_account_id_fkey;
END $$;

CREATE INDEX IF NOT EXISTS idx_expenses_financial_account
    ON public.expenses(workspace_id, financial_account_id) WHERE financial_account_id IS NOT NULL;

COMMENT ON COLUMN public.expenses.financial_account_id IS
    'The account or card the user says paid this expense (same workspace, checked by the backend). '
    'NULL: not told, never inferred.';

COMMIT;
