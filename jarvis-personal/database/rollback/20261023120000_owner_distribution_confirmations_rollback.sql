-- Rollback of 20261023120000_owner_distribution_confirmations.sql.
--
-- Removes the confirmations table and restores dincr_delete_guard_tables() to its 20261002150000
-- list. The debt payments, Salvavidas deposits, goal contributions and investment reserves that
-- confirmations produced are ordinary records and are NOT touched.
--
-- PRE-ROLLBACK GATE: the code that writes this table is reverted first. This file refuses to drop
-- confirmations that exist (PR010): export or delete them deliberately first, so evidence is never
-- lost by a rollback. BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF to_regclass('public.owner_distribution_confirmations') IS NOT NULL AND EXISTS (SELECT 1 FROM public.owner_distribution_confirmations) THEN
        RAISE EXCEPTION 'owner_distribution_confirmations has rows: export or delete them deliberately before rolling back' USING ERRCODE = 'PR010';
    END IF;
END $$;

DROP TABLE IF EXISTS public.owner_distribution_confirmations;

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
        ('email_ingested_messages'),
        -- 20261002150000: payroll receipt evidence and its trusted senders.
        ('payroll_receipts'),
        ('payroll_receipt_lines'),
        ('payroll_trusted_senders')
    ) AS t(table_name)
$fn$;
REVOKE ALL ON FUNCTION public.dincr_delete_guard_tables() FROM PUBLIC, anon, authenticated;

COMMIT;
