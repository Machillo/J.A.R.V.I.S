-- Whether DINCR knows a debt's interest rate was really given or confirmed (UNKNOWN ≠ 0%).
--
-- `debts.interest_rate` alone can't tell an unknown rate from a real 0%: create_user_debt used
-- to store "no rate given" as 0. From this migration on the writers set the new column:
--   interest_rate NULL, interest_rate_known FALSE  → unknown rate
--   interest_rate 0,    interest_rate_known TRUE   → a known 0%
--   interest_rate > 0,  interest_rate_known TRUE   → a known rate
-- Existing rows keep interest_rate_known NULL ("not verified"): the code reads them as before
-- the column existed — a rate above 0 is known; a 0 is unknown unless debt_type is 'tasa_cero'
-- (backend/user_product/debt_rates.py). No row is rewritten: reconciling historical 0s is a
-- later, separate decision.
--
-- Additive and idempotent: ADD COLUMN IF NOT EXISTS, nullable, no default (a catalog-only
-- change: no table rewrite, no backfill, no historical 0 becomes TRUE). It never drops, updates
-- or deletes. One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
-- PRE-MERGE GATE: the backend that reads and writes the column must not run before this is applied.
--
-- Preflight (read-only): must return zero rows. A missing table, or the column already present
-- (added by hand: IF NOT EXISTS would keep its type and data), means stop and investigate.
--   SELECT 'missing table' WHERE to_regclass('public.debts') IS NULL
--   UNION ALL
--   SELECT 'column already exists: ' || data_type FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'interest_rate_known';
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback (manual, human decision): database/rollback/20261006120000_debt_interest_rate_known_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE public.debts ADD COLUMN IF NOT EXISTS interest_rate_known BOOLEAN;

COMMENT ON COLUMN public.debts.interest_rate_known IS
    'TRUE: the rate was given or confirmed (0 is a real 0%). FALSE: unknown (rate NULL). '
    'NULL: written before 20261006120000, not verified (see backend/user_product/debt_rates.py).';

COMMIT;

-- Postflight (read-only): must return zero rows right after applying (the column exists, is a
-- nullable boolean, and no existing row was marked).
SELECT 'column missing or wrong type' AS problem
WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'interest_rate_known'
      AND data_type = 'boolean' AND is_nullable = 'YES' AND column_default IS NULL
)
UNION ALL
SELECT 'existing rows were marked: ' || count(*) FROM public.debts WHERE interest_rate_known IS NOT NULL
HAVING count(*) > 0;
