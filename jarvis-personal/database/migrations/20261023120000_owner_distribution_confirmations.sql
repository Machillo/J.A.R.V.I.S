-- Owner distribution confirmations: the exact-amount distributions the Owner declared carried out.
--
-- The exact-amount distribution is a planning answer and writes nothing. CONFIRMAR records that
-- the Owner followed it: one row per confirmation, written in the same transaction as the real
-- records it produced (extra debt payments, the Salvavidas deposit, the goal contribution, the
-- investment reserve), so a confirmation exists only when everything it applied exists.
-- - confirmation_key: chosen by the app for one reviewed distribution; unique per workspace, so
--   repeating it (double tap, retry) never applies the distribution twice.
-- - items: the split the Owner confirmed (destination -> amount); applied: what was written.
-- Workspace-owned evidence: the delete / truncate / workspace-move guards of 20260925140000 apply,
-- and dincr_app gets exactly what the code runs (SELECT, INSERT, UPDATE of the row it just
-- inserted; its id sequence), with RLS. No DELETE. No existing row is changed.
--
-- PRE-APPLY GATE: 20260925140000 (ownership guards), 20260926150000 (dincr_app) and
-- 20261002150000 (payroll receipts, the previous delete-guard list) applied. Aborts otherwise
-- (PR001 / PR002) and changes nothing.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, before the code
-- that writes this table is deployed.
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20261023120000_owner_distribution_confirmations_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RAISE EXCEPTION 'role dincr_app is missing: apply 20260926150000 first' USING ERRCODE = 'PR002';
    END IF;
    IF to_regproc('public.dincr_guard_financial_delete') IS NULL OR to_regproc('public.dincr_guard_workspace_move') IS NULL
       OR to_regclass('public.workspaces') IS NULL OR to_regclass('public.payroll_receipts') IS NULL THEN
        RAISE EXCEPTION 'ownership guards or payroll receipts missing: apply 20260925140000 and 20261002150000 first' USING ERRCODE = 'PR001';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.owner_distribution_confirmations (
    id                BIGSERIAL PRIMARY KEY,
    workspace_id      UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    confirmation_key  TEXT NOT NULL CHECK (confirmation_key ~ '^[A-Za-z0-9_-]{8,80}$'),
    amount            NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    currency          TEXT NOT NULL DEFAULT 'CRC' CHECK (currency = 'CRC'),
    items             JSONB NOT NULL,
    applied           JSONB,
    confirmed_by      TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_owner_distribution_confirmations_key UNIQUE (workspace_id, confirmation_key)
);

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
        -- 20261023120000: the Owner's confirmed distributions.
        ('owner_distribution_confirmations')
    ) AS t(table_name)
$fn$;
REVOKE ALL ON FUNCTION public.dincr_delete_guard_tables() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE TRIGGER trg_owner_distribution_confirmations_delete_guard AFTER DELETE ON public.owner_distribution_confirmations
    REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT EXECUTE FUNCTION public.dincr_guard_financial_delete();
CREATE OR REPLACE TRIGGER trg_owner_distribution_confirmations_truncate_guard BEFORE TRUNCATE ON public.owner_distribution_confirmations
    FOR EACH STATEMENT EXECUTE FUNCTION public.dincr_guard_financial_truncate();
CREATE OR REPLACE TRIGGER trg_owner_distribution_confirmations_workspace_move_guard BEFORE UPDATE OF workspace_id ON public.owner_distribution_confirmations
    FOR EACH ROW EXECUTE FUNCTION public.dincr_guard_workspace_move();

-- Runtime access: exactly what the code runs (no DELETE: confirmations are evidence).
GRANT SELECT, INSERT, UPDATE ON TABLE public.owner_distribution_confirmations TO dincr_app;
GRANT USAGE ON SEQUENCE public.owner_distribution_confirmations_id_seq TO dincr_app;
REVOKE ALL ON TABLE public.owner_distribution_confirmations FROM anon, authenticated;

ALTER TABLE public.owner_distribution_confirmations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dincr_app_access ON public.owner_distribution_confirmations;
CREATE POLICY dincr_app_access ON public.owner_distribution_confirmations AS PERMISSIVE FOR ALL TO dincr_app USING (true) WITH CHECK (true);

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'missing owner_distribution_confirmations' WHERE to_regclass('public.owner_distribution_confirmations') IS NULL
-- UNION ALL SELECT 'dincr_app lacks ' || p FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE']) p
--   WHERE NOT has_table_privilege('dincr_app', 'public.owner_distribution_confirmations', p)
-- UNION ALL SELECT 'dincr_app has extra DELETE' WHERE has_table_privilege('dincr_app', 'public.owner_distribution_confirmations', 'DELETE')
-- UNION ALL SELECT r || ' has access' FROM unnest(ARRAY['anon', 'authenticated']) r
--   WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) AND has_table_privilege(r, 'public.owner_distribution_confirmations', 'SELECT')
-- UNION ALL SELECT 'missing delete guard' WHERE NOT EXISTS (SELECT 1 FROM pg_trigger
--   WHERE tgrelid = 'public.owner_distribution_confirmations'::regclass AND tgname = 'trg_owner_distribution_confirmations_delete_guard')
-- UNION ALL SELECT 'RLS off' WHERE NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.owner_distribution_confirmations'::regclass);
