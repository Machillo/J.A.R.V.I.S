-- MANUAL rollback of 20261022150000_owner_recurring_automation.sql.
-- Human decision only; never run automatically.
--
-- Precondition: production no longer runs a backend that reads or writes the recurring
-- automation (roll the code back first). Otherwise the recurring screen, the Owner strategy and
-- the daily job fail.
--
-- What it does: no transaction is deleted. The incomes and installments the automation recorded
-- stay in `transactions` (they are the Owner's history). The occurrence log is kept first in a
-- closed snapshot table, as evidence; then the new columns, the table, the installment index
-- and the delete-guard entry leave. Dropping columns is catalog-only: no table rewrite.
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
--   SELECT 'still there ' || c FROM unnest(ARRAY['start_date', 'next_due_date', 'financial_account_id', 'auto_record']) c
--     WHERE EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
--                   AND table_name = 'finva_recurring_items' AND column_name = c)
--   UNION ALL SELECT 'still there recurring_item_occurrences' WHERE to_regclass('public.recurring_item_occurrences') IS NOT NULL
--   UNION ALL SELECT 'still there transactions_auto_debt_schedule_once'
--     WHERE to_regclass('public.transactions_auto_debt_schedule_once') IS NOT NULL;

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $$
BEGIN
    IF to_regclass('public.recurring_item_occurrences') IS NOT NULL THEN
        CREATE TABLE IF NOT EXISTS public.recurring_item_occurrences_rollback_snapshot AS
            SELECT * FROM public.recurring_item_occurrences WITH NO DATA;
        INSERT INTO public.recurring_item_occurrences_rollback_snapshot
            SELECT o.* FROM public.recurring_item_occurrences o
            WHERE NOT EXISTS (SELECT 1 FROM public.recurring_item_occurrences_rollback_snapshot s WHERE s.id = o.id);
        REVOKE ALL ON TABLE public.recurring_item_occurrences_rollback_snapshot FROM PUBLIC, anon, authenticated, dincr_app;
    END IF;
END $$;

-- The delete-guard list as 20261002150000 left it.
CREATE OR REPLACE FUNCTION public.dincr_delete_guard_tables()
RETURNS TABLE (table_name TEXT)
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT o.table_name FROM public.dincr_ownership_tables() o
    UNION ALL
    SELECT t.table_name FROM (VALUES
        ('finva_budget_items'),
        ('finva_recurring_items'),
        ('finva_goal_contributions'),
        ('finva_savings_plans'),
        ('finva_savings_plan_contributions'),
        ('financial_profiles'),
        ('card_aliases'),
        ('financial_input_events'),
        ('email_transaction_candidates'),
        ('email_statement_documents'),
        ('email_statement_reconciliation_lines'),
        ('email_financial_accounts'),
        ('finva_email_candidates'),
        ('finva_statement_documents'),
        ('investment_position_snapshots'),
        ('finva_gmail_connections'),
        ('finva_email_messages'),
        ('email_ingested_messages'),
        ('payroll_receipts'),
        ('payroll_receipt_lines'),
        ('payroll_trusted_senders')
    ) AS t(table_name)
$fn$;
REVOKE ALL ON FUNCTION public.dincr_delete_guard_tables() FROM PUBLIC, anon, authenticated;

DROP TABLE IF EXISTS public.recurring_item_occurrences;
DROP INDEX IF EXISTS public.transactions_auto_debt_schedule_once;
ALTER TABLE public.finva_recurring_items DROP CONSTRAINT IF EXISTS finva_recurring_items_auto_record_shape;
ALTER TABLE public.finva_recurring_items
    DROP COLUMN IF EXISTS auto_record,
    DROP COLUMN IF EXISTS financial_account_id,
    DROP COLUMN IF EXISTS next_due_date,
    DROP COLUMN IF EXISTS start_date;

COMMIT;
