-- Rollback of 20261002150000_payroll_receipts.sql.
--
-- Removes the payroll receipt and trusted-sender tables, their functions and triggers (including the one on
-- transactions), and restores dincr_delete_guard_tables() to its 20260925140000 list.
-- No transaction, debt or other row is touched: receipts only ever explained transactions.
--
-- PRE-ROLLBACK GATE: the code that reads these tables is reverted first. This file refuses
-- to drop receipts that exist (PR010): export or delete them deliberately first, so evidence
-- is never lost by a rollback. BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF to_regclass('public.payroll_receipts') IS NOT NULL AND EXISTS (SELECT 1 FROM public.payroll_receipts) THEN
        RAISE EXCEPTION 'payroll_receipts has rows: export or delete them deliberately before rolling back' USING ERRCODE = 'PR010';
    END IF;
END $$;

DROP TRIGGER IF EXISTS trg_transactions_payroll_receipt ON public.transactions;
DROP TABLE IF EXISTS public.payroll_receipt_lines;
DROP TABLE IF EXISTS public.payroll_receipts;
DROP TABLE IF EXISTS public.payroll_trusted_senders;
DROP FUNCTION IF EXISTS public.dincr_payroll_receipt_link();
DROP FUNCTION IF EXISTS public.dincr_payroll_receipt_transaction_changed();
DROP FUNCTION IF EXISTS public.dincr_payroll_receipt_line_debt();
DROP FUNCTION IF EXISTS public.dincr_payroll_receipt_totals();

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
        -- Parents whose deletes cascade into guarded tables row by row (a cascade
        -- fires the child's statement trigger once per parent row), so they carry
        -- the one-owner check themselves.
        ('finva_gmail_connections'),
        ('finva_email_messages'),
        ('email_ingested_messages')
    ) AS t(table_name)
$fn$;
REVOKE ALL ON FUNCTION public.dincr_delete_guard_tables() FROM PUBLIC, anon, authenticated;

COMMIT;
