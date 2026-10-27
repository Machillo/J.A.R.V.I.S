-- A manual expense typed in the other currency may wait for its conversion (USD until the close).
--
-- Today `expenses.amount` is always in the account's base currency, and an expense typed in the
-- other supported currency stores what the user typed (original_amount, original_currency) and
-- the rate the user entered (exchange_rate). The user now keeps dollar expenses in dollars until
-- the close (the card's statement cut, or the calendar month without a card), when one rate
-- converts them. Until then such an expense is "pending conversion": original_currency and
-- original_amount are set, amount and exchange_rate are NULL. Unknown is not zero: DINCR never
-- stores 0 colones for it and never invents a rate.
--
-- This migration only lets that state exist:
--   - `amount` drops NOT NULL (catalog-only: no table rewrite);
--   - expenses_original_currency_check gains the pending state as its third valid shape;
--   - expenses_amount_known_or_pending_check: an expense without amount must be pending (it can
--     never be "no amount at all");
--   - a partial index finds a workspace's pending expenses (the close reads exactly those).
-- Every existing row has amount set and keeps its meaning: no backfill, no update. Old code never
-- writes a NULL amount, so this is safe before the code that writes pending expenses deploys; that
-- code must read a NULL amount as "pending", never as 0.
--
-- One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate). The
-- constraints are added NOT VALID, then validated (every existing row already satisfies them).
--
-- Preflight (read-only): must return zero rows. A missing table or constraint, `amount` already
-- nullable, a new constraint already present, or a row that would not validate means stop.
--   SELECT 'missing table' AS problem WHERE to_regclass('public.expenses') IS NULL
--   UNION ALL
--   SELECT 'amount already nullable' FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'expenses' AND column_name = 'amount' AND is_nullable = 'YES'
--   UNION ALL
--   SELECT 'original currency check missing'
--   WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'expenses_original_currency_check'
--                     AND conrelid = 'public.expenses'::regclass)
--   UNION ALL
--   SELECT 'constraint already exists: ' || conname FROM pg_constraint
--   WHERE conrelid = 'public.expenses'::regclass AND conname = 'expenses_amount_known_or_pending_check'
--   UNION ALL
--   SELECT 'rows without amount: ' || count(*) FROM public.expenses WHERE amount IS NULL HAVING count(*) > 0;
-- Postflight (read-only, run after COMMIT as its own query): must return zero rows — amount is
-- nullable, both constraints are validated with the pending shape, the index exists, and no row
-- became pending.
--   SELECT 'amount still NOT NULL' AS problem FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'expenses' AND column_name = 'amount' AND is_nullable = 'NO'
--   UNION ALL
--   SELECT 'constraint missing or not validated: ' || name
--   FROM unnest(ARRAY['expenses_original_currency_check', 'expenses_amount_known_or_pending_check']) AS name
--   WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = name
--                     AND conrelid = 'public.expenses'::regclass AND convalidated)
--   UNION ALL
--   SELECT 'original currency check has no pending shape'
--   WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'expenses_original_currency_check'
--                     AND conrelid = 'public.expenses'::regclass
--                     AND pg_get_constraintdef(oid) LIKE '%amount IS NULL%')
--   UNION ALL
--   SELECT 'index missing' WHERE to_regclass('public.idx_expenses_pending_conversion') IS NULL
--   UNION ALL
--   SELECT 'rows became pending: ' || count(*) FROM public.expenses WHERE amount IS NULL HAVING count(*) > 0;
-- Rollback (manual, human decision): database/rollback/20261027120000_expense_pending_conversion_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE public.expenses ALTER COLUMN amount DROP NOT NULL;

-- The same two shapes as before, plus "pending conversion".
ALTER TABLE public.expenses DROP CONSTRAINT IF EXISTS expenses_original_currency_check;
ALTER TABLE public.expenses ADD CONSTRAINT expenses_original_currency_check CHECK (
    (original_currency IS NULL AND original_amount IS NULL AND exchange_rate IS NULL)
    OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NOT NULL
        AND original_currency IN ('CRC', 'USD') AND original_amount > 0 AND exchange_rate > 0)
    OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NULL AND amount IS NULL
        AND original_currency IN ('CRC', 'USD') AND original_amount > 0)
) NOT VALID;
ALTER TABLE public.expenses VALIDATE CONSTRAINT expenses_original_currency_check;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'expenses_amount_known_or_pending_check' AND conrelid = 'public.expenses'::regclass
    ) THEN
        ALTER TABLE public.expenses ADD CONSTRAINT expenses_amount_known_or_pending_check
            CHECK (amount IS NOT NULL OR (original_amount IS NOT NULL AND exchange_rate IS NULL)) NOT VALID;
    END IF;
    ALTER TABLE public.expenses VALIDATE CONSTRAINT expenses_amount_known_or_pending_check;
END $$;

CREATE INDEX IF NOT EXISTS idx_expenses_pending_conversion
    ON public.expenses(workspace_id, created_at) WHERE amount IS NULL;

COMMENT ON COLUMN public.expenses.amount IS
    'Amount in the account base currency. NULL only while an expense typed in the other currency '
    'waits for its conversion at the close (original_amount set, exchange_rate NULL): unknown, never 0.';

COMMIT;
