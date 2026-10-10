-- Whether DINCR knows a debt's monthly payment (UNKNOWN ≠ 0).
--
-- `debts.monthly_payment` is NOT NULL and create_user_debt / update_user_debt stored "no payment
-- given" as 0, so an unknown payment could not be told from a real 0. From this migration on the
-- Users writers set the new column:
--   monthly_payment 0,  monthly_payment_known FALSE → unknown (the 0 is a placeholder, never a payment)
--   monthly_payment 0,  monthly_payment_known TRUE  → a known 0
--   monthly_payment > 0, monthly_payment_known TRUE → a known payment
-- Existing rows keep monthly_payment_known NULL ("not verified") and are read exactly as before
-- (backend/user_product/debt_payments.py): no row is reinterpreted or rewritten. The Owner's own
-- finance paths never write the column. monthly_payment stays NOT NULL, so no engine reads a NULL.
--
-- Additive and idempotent: ADD COLUMN IF NOT EXISTS, nullable, no default (a catalog-only
-- change: no table rewrite, no backfill). It never drops, updates or deletes. One transaction:
-- apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
-- PRE-MERGE GATE: the backend that reads and writes the column must not run before this is applied.
--
-- Preflight (read-only): must return zero rows. A missing table, or the column already present
-- (added by hand: IF NOT EXISTS would keep its type and data), means stop and investigate.
--   SELECT 'missing table' WHERE to_regclass('public.debts') IS NULL
--   UNION ALL
--   SELECT 'column already exists: ' || data_type FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'monthly_payment_known';
-- Postflight (read-only, run after COMMIT as its own query): must return zero rows — the
-- column exists as a nullable boolean with no default, and no existing row was marked.
--   SELECT 'column missing or wrong type' AS problem
--   WHERE NOT EXISTS (
--       SELECT 1 FROM information_schema.columns
--       WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'monthly_payment_known'
--         AND data_type = 'boolean' AND is_nullable = 'YES' AND column_default IS NULL
--   )
--   UNION ALL
--   SELECT 'existing rows were marked: ' || count(*) FROM public.debts WHERE monthly_payment_known IS NOT NULL
--   HAVING count(*) > 0;
-- Rollback (manual, human decision): database/rollback/20261010120000_debt_monthly_payment_known_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE public.debts ADD COLUMN IF NOT EXISTS monthly_payment_known BOOLEAN;

COMMENT ON COLUMN public.debts.monthly_payment_known IS
    'TRUE: the monthly payment was given (0 is a real 0). FALSE: unknown (the stored 0 is a placeholder). '
    'NULL: written before 20261010120000 or by the Owner finance paths, read as stored (see backend/user_product/debt_payments.py).';

COMMIT;
