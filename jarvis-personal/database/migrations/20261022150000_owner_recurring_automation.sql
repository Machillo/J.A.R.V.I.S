-- Owner recurring automation: fixed recurring incomes and scheduled debt installments recorded
-- once, on their due date (Costa Rica), for the verified Owner only.
--
-- - finva_recurring_items gains what a recurring income needs to be recorded on its date:
--     start_date            first date of the series (informational; editable);
--     next_due_date         the next date DINCR expects it (the automation's cursor);
--     financial_account_id  the account it lands in, when known (account_balances of the same
--                           workspace; NULL = unknown, never invented);
--     auto_record           record it as an income transaction on each due date. The backend
--                           accepts TRUE only for the verified Owner, only for incomes, never for
--                           salary categories (salary keeps coming from payroll and the deposit).
--   Existing rows keep auto_record = FALSE: nothing is recorded until the Owner turns it on.
-- - recurring_item_occurrences: one row per (item, due date) the automation handled, with the
--   transaction it recorded, or the existing transaction it recognised as that same income
--   (already_recorded: e.g. the deposit arrived by mail first). UNIQUE (workspace_id, item_id,
--   due_date) makes a second run, or two concurrent runs, record nothing twice. Rows are history:
--   deleting the recurring item keeps them (item_id SET NULL) and keeps its transactions.
-- - transactions: a unique partial index on the scheduled debt installment notes
--   (source 'auto_debt_schedule', notes 'debt_id:X;installment:N'), so the installment engine's
--   NOT EXISTS check also holds under concurrency. Production has no such rows (checked
--   2026-10-22); the index aborts the migration (unique violation) instead of hiding duplicates.
-- No existing row is changed. dincr_app gets exactly what the code runs on the new table
-- (SELECT, INSERT, UPDATE; no DELETE: occurrences are history), with RLS.
--
-- PRE-APPLY GATE: 20260925140000 (ownership guards), 20260925130000 (finva_recurring_items),
-- 20260926150000 (dincr_app) and 20261002150000 (delete-guard list) applied. Aborts otherwise
-- (PR001 / PR002) and changes nothing.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, before the code
-- that reads these columns is deployed.
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20261022150000_owner_recurring_automation_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RAISE EXCEPTION 'role dincr_app is missing: apply 20260926150000 first' USING ERRCODE = 'PR002';
    END IF;
    IF to_regproc('public.dincr_guard_financial_delete') IS NULL OR to_regproc('public.dincr_guard_workspace_move') IS NULL
       OR to_regproc('public.dincr_delete_guard_tables') IS NULL
       OR to_regclass('public.finva_recurring_items') IS NULL OR to_regclass('public.transactions') IS NULL
       OR to_regclass('public.account_balances') IS NULL OR to_regclass('public.payroll_receipts') IS NULL THEN
        RAISE EXCEPTION 'ownership guards or base tables missing: apply 20260925140000, 20260925130000 and 20261002150000 first'
            USING ERRCODE = 'PR001';
    END IF;
END $$;

ALTER TABLE public.finva_recurring_items
    ADD COLUMN IF NOT EXISTS start_date DATE,
    ADD COLUMN IF NOT EXISTS next_due_date DATE,
    ADD COLUMN IF NOT EXISTS financial_account_id BIGINT REFERENCES public.account_balances(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS auto_record BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'finva_recurring_items_auto_record_shape') THEN
        -- Only an income with a next date can be recorded automatically.
        ALTER TABLE public.finva_recurring_items ADD CONSTRAINT finva_recurring_items_auto_record_shape
            CHECK (NOT auto_record OR (item_type = 'income' AND next_due_date IS NOT NULL));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.recurring_item_occurrences (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    item_id         BIGINT REFERENCES public.finva_recurring_items(id) ON DELETE SET NULL,
    item_name       TEXT NOT NULL,
    due_date        DATE NOT NULL,
    amount          NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    status          TEXT NOT NULL CHECK (status IN ('recorded', 'already_recorded')),
    transaction_id  BIGINT REFERENCES public.transactions(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, item_id, due_date)
);
CREATE INDEX IF NOT EXISTS recurring_item_occurrences_workspace_due
    ON public.recurring_item_occurrences (workspace_id, due_date);

-- A scheduled installment is one transaction, also under concurrent runs.
CREATE UNIQUE INDEX IF NOT EXISTS transactions_auto_debt_schedule_once
    ON public.transactions (workspace_id, notes) WHERE source = 'auto_debt_schedule';

-- Financial-evidence guards of 20260925140000 (one owner per delete, no truncate, no moves).
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
        ('payroll_trusted_senders'),
        -- 20261022150000: what the recurring automation recorded.
        ('recurring_item_occurrences')
    ) AS t(table_name)
$fn$;
REVOKE ALL ON FUNCTION public.dincr_delete_guard_tables() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE TRIGGER trg_recurring_item_occurrences_delete_guard AFTER DELETE ON public.recurring_item_occurrences
    REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT EXECUTE FUNCTION public.dincr_guard_financial_delete();
CREATE OR REPLACE TRIGGER trg_recurring_item_occurrences_truncate_guard BEFORE TRUNCATE ON public.recurring_item_occurrences
    FOR EACH STATEMENT EXECUTE FUNCTION public.dincr_guard_financial_truncate();
CREATE OR REPLACE TRIGGER trg_recurring_item_occurrences_workspace_move_guard BEFORE UPDATE OF workspace_id ON public.recurring_item_occurrences
    FOR EACH ROW EXECUTE FUNCTION public.dincr_guard_workspace_move();

-- Runtime access: exactly what the code runs (no DELETE: occurrences are history).
GRANT SELECT, INSERT, UPDATE ON TABLE public.recurring_item_occurrences TO dincr_app;
GRANT USAGE ON SEQUENCE public.recurring_item_occurrences_id_seq TO dincr_app;
REVOKE ALL ON TABLE public.recurring_item_occurrences FROM anon, authenticated;

ALTER TABLE public.recurring_item_occurrences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dincr_app_access ON public.recurring_item_occurrences;
CREATE POLICY dincr_app_access ON public.recurring_item_occurrences AS PERMISSIVE FOR ALL TO dincr_app USING (true) WITH CHECK (true);

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'missing column ' || c FROM unnest(ARRAY['start_date', 'next_due_date', 'financial_account_id', 'auto_record']) c
--   WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
--                     AND table_name = 'finva_recurring_items' AND column_name = c)
-- UNION ALL SELECT 'missing recurring_item_occurrences' WHERE to_regclass('public.recurring_item_occurrences') IS NULL
-- UNION ALL SELECT 'missing transactions_auto_debt_schedule_once' WHERE to_regclass('public.transactions_auto_debt_schedule_once') IS NULL
-- UNION ALL SELECT 'dincr_app lacks ' || p FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE']) p
--   WHERE NOT has_table_privilege('dincr_app', 'public.recurring_item_occurrences', p)
-- UNION ALL SELECT 'dincr_app has DELETE on recurring_item_occurrences'
--   WHERE has_table_privilege('dincr_app', 'public.recurring_item_occurrences', 'DELETE')
-- UNION ALL SELECT 'auto_record already on for ' || count(*) FROM public.finva_recurring_items WHERE auto_record HAVING count(*) > 0;
