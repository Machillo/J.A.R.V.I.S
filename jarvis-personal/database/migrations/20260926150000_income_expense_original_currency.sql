-- Original currency of manual income (salaries) and expenses.
--
-- Same model as transactions: `amount` stays in the account's base currency, so
-- every existing total keeps its meaning. An entry typed in the other supported
-- currency also stores what the user typed (original_amount, original_currency)
-- and the exchange rate the user entered (CRC per 1 USD). DINCR never invents a
-- rate. NULL in the three columns means the entry was made in the base currency,
-- which is how every existing row is read: no backfill, no rewrite.
--
-- Idempotent and additive: ADD COLUMN IF NOT EXISTS (nullable, no default: a
-- catalog-only change) and CHECK constraints added NOT VALID then validated.
-- It never drops, rewrites or deletes. One transaction: apply it with
-- backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
--
-- Preflight (read-only): both tables exist.
--   SELECT t FROM unnest(ARRAY['salaries','expenses']) t
--   WHERE to_regclass('public.' || t) IS NULL;
-- Postflight: the query at the end of this file returns zero rows.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE public.salaries
    ADD COLUMN IF NOT EXISTS original_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS original_currency TEXT,
    ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(14, 6);

ALTER TABLE public.expenses
    ADD COLUMN IF NOT EXISTS original_amount NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS original_currency TEXT,
    ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(14, 6);

-- The three columns are all set (a foreign-currency entry) or all NULL.
DO $$
DECLARE
    target TEXT;
BEGIN
    FOREACH target IN ARRAY ARRAY['salaries', 'expenses'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = target || '_original_currency_check'
              AND conrelid = ('public.' || target)::regclass
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I CHECK ('
                '(original_currency IS NULL AND original_amount IS NULL AND exchange_rate IS NULL) '
                'OR (original_currency IN (''CRC'', ''USD'') AND original_amount > 0 AND exchange_rate > 0)'
                ') NOT VALID',
                target, target || '_original_currency_check'
            );
        END IF;
        EXECUTE format('ALTER TABLE public.%I VALIDATE CONSTRAINT %I', target, target || '_original_currency_check');
    END LOOP;
END $$;

COMMENT ON COLUMN public.salaries.original_currency IS 'Currency the user typed when it differs from the account base currency; NULL = base currency. amount is always in the base currency.';
COMMENT ON COLUMN public.salaries.exchange_rate IS 'User-entered CRC per 1 USD used to compute amount. Never invented by DINCR.';
COMMENT ON COLUMN public.expenses.original_currency IS 'Currency the user typed when it differs from the account base currency; NULL = base currency. amount is always in the base currency.';
COMMENT ON COLUMN public.expenses.exchange_rate IS 'User-entered CRC per 1 USD used to compute amount. Never invented by DINCR.';

COMMIT;

-- Postflight (read-only): must return zero rows.
--   SELECT c.table_name, c.column_name FROM (VALUES
--     ('salaries','original_amount'),('salaries','original_currency'),('salaries','exchange_rate'),
--     ('expenses','original_amount'),('expenses','original_currency'),('expenses','exchange_rate')
--   ) c(table_name, column_name)
--   WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns i
--                     WHERE i.table_schema='public' AND i.table_name=c.table_name AND i.column_name=c.column_name)
--   UNION ALL
--   SELECT t, 'constraint not validated' FROM unnest(ARRAY['salaries','expenses']) t
--   WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = t || '_original_currency_check' AND convalidated);
