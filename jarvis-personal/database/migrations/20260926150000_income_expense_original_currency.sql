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
-- Preflight (read-only): must return zero rows. A missing table, or one of the
-- new columns already present (added by hand: IF NOT EXISTS would keep its type
-- and data), means stop and investigate before applying.
--   SELECT t AS table_name, 'missing table' AS problem FROM unnest(ARRAY['salaries','expenses']) t
--   WHERE to_regclass('public.' || t) IS NULL
--   UNION ALL
--   SELECT table_name::text, 'column already exists: ' || column_name FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name IN ('salaries', 'expenses')
--     AND column_name IN ('original_amount', 'original_currency', 'exchange_rate');
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback (manual, human decision): database/rollback/20260926150000_income_expense_original_currency_rollback.sql

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

-- The three columns are all set (a foreign-currency entry) or all NULL. The
-- explicit IS NOT NULL matter: a CHECK passes when it evaluates to NULL, so
-- without them a partial triple (a currency and an amount without a rate, ...)
-- would be accepted.
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
                'OR (original_currency IS NOT NULL AND original_amount IS NOT NULL AND exchange_rate IS NOT NULL '
                'AND original_currency IN (''CRC'', ''USD'') AND original_amount > 0 AND exchange_rate > 0)'
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

-- Postflight (read-only): must return zero rows (each column present, nullable,
-- without a default and with its exact type; both constraints validated).
--   SELECT c.table_name, c.column_name FROM (VALUES
--     ('salaries','original_amount','numeric(14,2)'),('salaries','original_currency','text'),('salaries','exchange_rate','numeric(14,6)'),
--     ('expenses','original_amount','numeric(14,2)'),('expenses','original_currency','text'),('expenses','exchange_rate','numeric(14,6)')
--   ) c(table_name, column_name, column_type)
--   WHERE NOT EXISTS (SELECT 1 FROM pg_attribute a
--                     WHERE a.attrelid = ('public.' || c.table_name)::regclass AND a.attname = c.column_name
--                       AND NOT a.attisdropped AND NOT a.attnotnull AND NOT a.atthasdef
--                       AND format_type(a.atttypid, a.atttypmod) = c.column_type)
--   UNION ALL
--   SELECT t, 'constraint not validated' FROM unnest(ARRAY['salaries','expenses']) t
--   WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = t || '_original_currency_check' AND convalidated);
