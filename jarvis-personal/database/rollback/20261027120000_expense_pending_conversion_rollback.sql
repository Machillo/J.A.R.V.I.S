-- MANUAL rollback of 20261027120000_expense_pending_conversion.sql.
-- Human decision only; never run automatically.
--
-- Precondition: the code that records or closes pending (unconverted) expenses is rolled back first.
--
-- What it does: restores `amount NOT NULL`, the two-shape expenses_original_currency_check, and
-- drops the pending constraint and index. It never changes an expense. If any expense is still
-- pending (amount NULL), it ABORTS without changing anything: putting NOT NULL back would need a
-- colones amount, and DINCR never invents a rate or a 0. A person must first decide, with the
-- user, how each pending expense is converted (the close) or removed.
--
-- How to run it (apply_migration.py refuses files outside database/migrations, and
-- docs/security/migration-safety-protocol.md §2 allows this exception):
--   1. BACKUP_VERIFIED gate open for this database (db_backup_verify.py gate);
--   2. a second person reads this file and the reason for rolling back;
--   3. psql -v ON_ERROR_STOP=1 over a direct session connection as postgres,
--      one transaction (this file's BEGIN/COMMIT).
-- Idempotent: a second run finds the original state and changes nothing.
--
-- Postflight (read-only): must return zero rows.
--   SELECT 'amount nullable' AS problem FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'expenses' AND column_name = 'amount' AND is_nullable = 'YES'
--   UNION ALL
--   SELECT 'still present: ' || conname FROM pg_constraint
--   WHERE conrelid = 'public.expenses'::regclass AND conname = 'expenses_amount_known_or_pending_check'
--   UNION ALL
--   SELECT 'index still present' WHERE to_regclass('public.idx_expenses_pending_conversion') IS NOT NULL;

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $$
DECLARE
    pending BIGINT;
BEGIN
    SELECT count(*) INTO pending FROM public.expenses WHERE amount IS NULL;
    IF pending > 0 THEN
        RAISE EXCEPTION 'rollback refused: % expense(s) still pending conversion; resolve them first', pending;
    END IF;
END $$;

DROP INDEX IF EXISTS public.idx_expenses_pending_conversion;
ALTER TABLE public.expenses DROP CONSTRAINT IF EXISTS expenses_amount_known_or_pending_check;

ALTER TABLE public.expenses DROP CONSTRAINT IF EXISTS expenses_original_currency_check;
ALTER TABLE public.expenses ADD CONSTRAINT expenses_original_currency_check CHECK (
    (original_currency IS NULL AND original_amount IS NULL AND exchange_rate IS NULL)
    OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NOT NULL
        AND original_currency IN ('CRC', 'USD') AND original_amount > 0 AND exchange_rate > 0)
) NOT VALID;
ALTER TABLE public.expenses VALIDATE CONSTRAINT expenses_original_currency_check;

ALTER TABLE public.expenses ALTER COLUMN amount SET NOT NULL;

COMMENT ON COLUMN public.expenses.amount IS NULL;

COMMIT;
