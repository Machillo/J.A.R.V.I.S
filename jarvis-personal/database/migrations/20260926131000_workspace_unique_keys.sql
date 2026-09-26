-- Legacy identity retirement, phase E1 (b): every uniqueness rule scoped by the
-- legacy user_id gets the same rule scoped by workspace_id.
--
-- Once writers stop writing user_id, a unique index on (user_id, ...) stops
-- deduplicating (NULLs are distinct): a second monthly debt payment for the same
-- due date, a second fixed expense with the same name, and so on, would be accepted.
-- This migration adds the workspace-scoped twin of each such index (same columns
-- with workspace_id in place of user_id, same predicate). The user_id indexes stay
-- until the columns are retired. No row is changed.
--
-- Aborts (UK001), changing nothing, if existing rows already violate a new rule
-- (a human decides which row is right; never resolved here), and (UK002) if any
-- unique index on user_id still lacks a workspace twin afterwards.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, with
-- or after 20260926130000, and before the code that stops writing user_id is deployed.
--
-- Preflight (read-only): must return zero rows.
--   SELECT 'credit_card_settings' FROM public.credit_card_settings GROUP BY workspace_id, bank, card_last4
--    HAVING count(*) > 1 AND card_last4 IS NOT NULL
--   UNION ALL SELECT 'debt_payments' FROM public.debt_payments
--    WHERE payment_type = 'monthly_payment' AND payment_date IS NOT NULL
--    GROUP BY workspace_id, debt_id, payment_date HAVING count(*) > 1
--   UNION ALL SELECT 'fixed_expense_matches' FROM public.fixed_expense_matches
--    GROUP BY workspace_id, fixed_expense_id, period_month HAVING count(*) > 1
--   UNION ALL SELECT 'fixed_expenses' FROM public.fixed_expenses GROUP BY workspace_id, name HAVING count(*) > 1;
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926131000_workspace_unique_keys_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $$
DECLARE
    spec TEXT[];
    missing TEXT[];
BEGIN
    FOREACH spec SLICE 1 IN ARRAY ARRAY[
        ARRAY['credit_card_settings', 'uq_credit_card_settings_workspace_bank_card', '(workspace_id, bank, card_last4)', ''],
        ARRAY['debt_payments', 'uq_debt_payments_workspace_monthly_due', '(workspace_id, debt_id, payment_date)',
              'WHERE payment_type = ''monthly_payment'' AND payment_date IS NOT NULL'],
        ARRAY['fixed_expense_matches', 'uq_fixed_expense_matches_workspace_period', '(workspace_id, fixed_expense_id, period_month)', ''],
        ARRAY['fixed_expenses', 'uq_fixed_expenses_workspace_name', '(workspace_id, name)', '']]
    LOOP
        CONTINUE WHEN to_regclass('public.' || spec[1]) IS NULL OR to_regclass('public.' || spec[2]) IS NOT NULL;
        EXECUTE format('LOCK TABLE public.%I IN SHARE MODE', spec[1]);
        BEGIN
            EXECUTE format('CREATE UNIQUE INDEX %I ON public.%I %s %s', spec[2], spec[1], spec[3], spec[4]);
        EXCEPTION WHEN unique_violation THEN
            RAISE EXCEPTION 'rows in % already break the workspace rule %; resolve them first', spec[1], spec[3]
                USING ERRCODE = 'UK001';
        END;
    END LOOP;

    SELECT array_agg(DISTINCT c.relname::TEXT) INTO missing
    FROM pg_index x
    JOIN pg_class c ON c.oid = x.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(x.indkey) AND a.attname = 'user_id'
    WHERE x.indisunique AND c.relname NOT LIKE 'audit\_backup\_%'
      AND NOT EXISTS (
          SELECT 1 FROM pg_index y WHERE y.indrelid = x.indrelid AND y.indisunique AND y.indexrelid <> x.indexrelid
            AND regexp_replace(pg_get_indexdef(y.indexrelid), '^.* USING ', '')
              = replace(regexp_replace(pg_get_indexdef(x.indexrelid), '^.* USING ', ''), 'user_id', 'workspace_id'));
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'unique rules on user_id without a workspace twin: %', missing USING ERRCODE = 'UK002';
    END IF;
END $$;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'no workspace twin for ' || i.relname FROM pg_index x
--  JOIN pg_class c ON c.oid = x.indrelid
--  JOIN pg_class i ON i.oid = x.indexrelid
--  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
--  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(x.indkey) AND a.attname = 'user_id'
--  WHERE x.indisunique AND c.relname NOT LIKE 'audit\_backup\_%' AND NOT EXISTS (
--    SELECT 1 FROM pg_index y WHERE y.indrelid = x.indrelid AND y.indisunique AND y.indexrelid <> x.indexrelid
--      AND regexp_replace(pg_get_indexdef(y.indexrelid), '^.* USING ', '')
--        = replace(regexp_replace(pg_get_indexdef(x.indexrelid), '^.* USING ', ''), 'user_id', 'workspace_id'));
