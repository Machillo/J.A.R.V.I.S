-- Payroll receipts: what a salary deposit was made of.
--
-- A payroll receipt (pay stub) EXPLAINS an income; the bank deposit IS the income. DINCR keeps
-- `transactions` as the only economic source: one salary = one `income` transaction (the net
-- deposited) + at most one receipt linked to it. Receipts and their lines are never summed as
-- income, spending, balance or debt by any report; they describe gross -> deductions -> net.
--
-- - payroll_receipts: one row per receipt (period, issue date, gross, deductions, net, source),
--   linked 1:1 to the transaction it explains (transaction_id). Invariants enforced here:
--     gross - deductions = net (to the cent);
--     MATCHED <=> linked to an `income` transaction of the same workspace whose amount = net;
--     a transaction explains at most one receipt; a receipt explains at most one transaction;
--     the same receipt (workspace, period, gross, net) or source message is stored once;
--     the lines add up to gross and deductions (checked at commit).
--   If a linked transaction is deleted or changed so that it no longer matches, the receipt
--   stays as evidence and drops to UNRESOLVED (never silently MATCHED).
-- - payroll_receipt_lines: each line as printed (income or deduction), with its generic kind
--   and hours. Deductions never move money: a loan repaid through payroll may point to its
--   debt (debt_id) for reconciliation only; it is not an expense and not a debt payment.
-- - payroll_trusted_senders: which mail senders a workspace trusts for payroll receipts (exact,
--   lower-case address; never a domain wildcard). A mail receipt is stored only when its sender
--   is trusted by THAT workspace; the parser alone never decides. Deactivated, not deleted.
-- The three tables are workspace-owned: the delete / truncate / workspace-move
-- guards of 20260925140000 apply to them, and dincr_app gets exactly what the code runs
-- (SELECT, INSERT, UPDATE on receipts and trusted senders; SELECT, INSERT on lines; their id
-- sequences), with RLS. No DELETE: receipts are evidence and trust is deactivated, not deleted.
-- No existing row is changed.
--
-- PRE-APPLY GATE: 20260925140000 (ownership guards) and 20260926150000 (dincr_app) applied.
-- Aborts otherwise (PR001 / PR002) and changes nothing.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, before the code
-- that reads these tables is deployed.
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20261002150000_payroll_receipts_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RAISE EXCEPTION 'role dincr_app is missing: apply 20260926150000 first' USING ERRCODE = 'PR002';
    END IF;
    IF to_regproc('public.dincr_guard_financial_delete') IS NULL OR to_regproc('public.dincr_guard_workspace_move') IS NULL
       OR to_regclass('public.transactions') IS NULL OR to_regclass('public.debts') IS NULL OR to_regclass('public.workspaces') IS NULL THEN
        RAISE EXCEPTION 'ownership guards or base tables missing: apply 20260925140000 first' USING ERRCODE = 'PR001';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.payroll_receipts (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    transaction_id  BIGINT REFERENCES public.transactions(id) ON DELETE SET NULL,
    period_code     TEXT,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    issue_date      DATE,
    currency        TEXT NOT NULL DEFAULT 'CRC',
    gross           NUMERIC(14,2) NOT NULL CHECK (gross >= 0),
    deductions      NUMERIC(14,2) NOT NULL CHECK (deductions >= 0),
    net             NUMERIC(14,2) NOT NULL,
    match_status    TEXT NOT NULL DEFAULT 'PAYROLL_ONLY'
                    CHECK (match_status IN ('MATCHED', 'POSSIBLE_MATCH', 'PAYROLL_ONLY', 'UNRESOLVED')),
    match_note      TEXT,
    source          TEXT NOT NULL,
    source_key      TEXT,
    source_address  TEXT,                      -- the trusted sender a mail receipt came from
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_payroll_receipts_mail_sender CHECK (source <> 'mail_receipt' OR source_address IS NOT NULL),
    CONSTRAINT ck_payroll_receipts_net CHECK (abs(gross - deductions - net) <= 0.01),
    CONSTRAINT ck_payroll_receipts_period CHECK (period_end >= period_start),
    CONSTRAINT ck_payroll_receipts_matched_link CHECK (match_status <> 'MATCHED' OR transaction_id IS NOT NULL),
    CONSTRAINT uq_payroll_receipts_id_workspace UNIQUE (id, workspace_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_receipts_transaction
    ON public.payroll_receipts(transaction_id) WHERE transaction_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_receipts_period
    ON public.payroll_receipts(workspace_id, period_start, period_end, gross, net);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_receipts_source
    ON public.payroll_receipts(workspace_id, source, source_key) WHERE source_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payroll_receipts_workspace_issue
    ON public.payroll_receipts(workspace_id, issue_date);

CREATE TABLE IF NOT EXISTS public.payroll_trusted_senders (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    sender_address  TEXT NOT NULL CHECK (sender_address = lower(btrim(sender_address)) AND sender_address ~ '^[a-z0-9_.+-]+@[a-z0-9.-]+$'),
    label           TEXT,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_payroll_trusted_senders UNIQUE (workspace_id, sender_address)
);

CREATE TABLE IF NOT EXISTS public.payroll_receipt_lines (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    UUID NOT NULL,
    receipt_id      BIGINT NOT NULL,
    section         TEXT NOT NULL CHECK (section IN ('income', 'deduction')),
    kind            TEXT NOT NULL,
    label           TEXT NOT NULL,
    amount          NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    hours           NUMERIC(8,2) CHECK (hours IS NULL OR hours >= 0),
    debt_id         BIGINT REFERENCES public.debts(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (receipt_id, workspace_id) REFERENCES public.payroll_receipts(id, workspace_id) ON DELETE CASCADE,
    CONSTRAINT ck_payroll_receipt_lines_kind CHECK (
        (section = 'income' AND kind IN ('ordinary', 'overtime', 'holiday_paid', 'holiday_worked', 'vacation', 'bonus', 'other_income'))
        OR (section = 'deduction' AND kind IN ('social_security', 'income_tax', 'association', 'loan_repayment', 'other_deduction'))),
    CONSTRAINT ck_payroll_receipt_lines_debt_only_loans CHECK (debt_id IS NULL OR kind = 'loan_repayment')
);
CREATE INDEX IF NOT EXISTS idx_payroll_receipt_lines_receipt ON public.payroll_receipt_lines(workspace_id, receipt_id);

-- A receipt's link: same workspace, an income, and (when MATCHED) exactly its net amount.
CREATE OR REPLACE FUNCTION public.dincr_payroll_receipt_link()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    tx RECORD;
BEGIN
    NEW.updated_at := NOW();
    IF NEW.transaction_id IS NULL THEN
        IF TG_OP = 'UPDATE' AND NEW.match_status = 'MATCHED' THEN   -- the deposit was deleted (ON DELETE SET NULL)
            NEW.match_status := 'UNRESOLVED';
            NEW.match_note := 'linked transaction removed';
        END IF;
        RETURN NEW;
    END IF;
    SELECT t.workspace_id, t.amount, t.transaction_type INTO tx FROM public.transactions t WHERE t.id = NEW.transaction_id;
    IF tx.workspace_id IS DISTINCT FROM NEW.workspace_id THEN
        RAISE EXCEPTION 'payroll receipt linked to a transaction of another workspace' USING ERRCODE = '23514';
    END IF;
    IF NEW.match_status = 'MATCHED' AND (tx.transaction_type IS DISTINCT FROM 'income' OR abs(tx.amount - NEW.net) > 0.005) THEN
        RAISE EXCEPTION 'a MATCHED payroll receipt must link an income whose amount equals its net' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$fn$;
REVOKE ALL ON FUNCTION public.dincr_payroll_receipt_link() FROM PUBLIC, anon, authenticated;
CREATE OR REPLACE TRIGGER trg_payroll_receipts_link BEFORE INSERT OR UPDATE ON public.payroll_receipts
    FOR EACH ROW EXECUTE FUNCTION public.dincr_payroll_receipt_link();

-- A linked transaction that stops matching (amount or type changed) leaves the receipt UNRESOLVED.
CREATE OR REPLACE FUNCTION public.dincr_payroll_receipt_transaction_changed()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    UPDATE public.payroll_receipts r
       SET match_status = 'UNRESOLVED', match_note = 'linked transaction changed'
     WHERE r.transaction_id = NEW.id AND r.match_status = 'MATCHED'
       AND (NEW.transaction_type IS DISTINCT FROM 'income' OR abs(NEW.amount - r.net) > 0.005);
    RETURN NEW;
END
$fn$;
REVOKE ALL ON FUNCTION public.dincr_payroll_receipt_transaction_changed() FROM PUBLIC, anon, authenticated;
CREATE OR REPLACE TRIGGER trg_transactions_payroll_receipt AFTER UPDATE OF amount, transaction_type ON public.transactions
    FOR EACH ROW WHEN (OLD.amount IS DISTINCT FROM NEW.amount OR OLD.transaction_type IS DISTINCT FROM NEW.transaction_type)
    EXECUTE FUNCTION public.dincr_payroll_receipt_transaction_changed();

-- A line's debt belongs to the same workspace.
CREATE OR REPLACE FUNCTION public.dincr_payroll_receipt_line_debt()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF NEW.debt_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.debts d WHERE d.id = NEW.debt_id AND d.workspace_id = NEW.workspace_id) THEN
        RAISE EXCEPTION 'payroll deduction linked to a debt of another workspace' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$fn$;
REVOKE ALL ON FUNCTION public.dincr_payroll_receipt_line_debt() FROM PUBLIC, anon, authenticated;
CREATE OR REPLACE TRIGGER trg_payroll_receipt_lines_debt BEFORE INSERT OR UPDATE OF debt_id, workspace_id ON public.payroll_receipt_lines
    FOR EACH ROW EXECUTE FUNCTION public.dincr_payroll_receipt_line_debt();

-- At commit, a receipt's lines add up to its gross and deductions.
CREATE OR REPLACE FUNCTION public.dincr_payroll_receipt_totals()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    rid BIGINT;
    r RECORD;
    income_sum NUMERIC;
    deduction_sum NUMERIC;
BEGIN
    -- NEW/OLD carry the firing table's columns only: branch before touching them.
    IF TG_TABLE_NAME = 'payroll_receipts' THEN
        rid := NEW.id;
    ELSIF TG_OP = 'DELETE' THEN
        rid := OLD.receipt_id;
    ELSE
        rid := NEW.receipt_id;
    END IF;
    SELECT p.gross, p.deductions INTO r FROM public.payroll_receipts p WHERE p.id = rid;
    IF NOT FOUND THEN
        RETURN NULL;   -- the receipt itself was deleted
    END IF;
    SELECT COALESCE(sum(l.amount) FILTER (WHERE l.section = 'income'), 0), COALESCE(sum(l.amount) FILTER (WHERE l.section = 'deduction'), 0)
      INTO income_sum, deduction_sum FROM public.payroll_receipt_lines l WHERE l.receipt_id = rid;
    IF abs(income_sum - r.gross) > 0.01 OR abs(deduction_sum - r.deductions) > 0.01 THEN
        RAISE EXCEPTION 'payroll receipt lines do not add up to its gross and deductions' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$fn$;
REVOKE ALL ON FUNCTION public.dincr_payroll_receipt_totals() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS trg_payroll_receipts_totals ON public.payroll_receipts;
CREATE CONSTRAINT TRIGGER trg_payroll_receipts_totals AFTER INSERT OR UPDATE OF gross, deductions ON public.payroll_receipts
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.dincr_payroll_receipt_totals();
DROP TRIGGER IF EXISTS trg_payroll_receipt_lines_totals ON public.payroll_receipt_lines;
CREATE CONSTRAINT TRIGGER trg_payroll_receipt_lines_totals AFTER INSERT OR UPDATE OR DELETE ON public.payroll_receipt_lines
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.dincr_payroll_receipt_totals();

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
        ('payroll_trusted_senders')
    ) AS t(table_name)
$fn$;
REVOKE ALL ON FUNCTION public.dincr_delete_guard_tables() FROM PUBLIC, anon, authenticated;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['payroll_receipts', 'payroll_receipt_lines', 'payroll_trusted_senders'] LOOP
        EXECUTE format('CREATE OR REPLACE TRIGGER %I AFTER DELETE ON public.%I REFERENCING OLD TABLE AS old_rows '
                       'FOR EACH STATEMENT EXECUTE FUNCTION public.dincr_guard_financial_delete()', 'trg_' || t || '_delete_guard', t);
        EXECUTE format('CREATE OR REPLACE TRIGGER %I BEFORE TRUNCATE ON public.%I '
                       'FOR EACH STATEMENT EXECUTE FUNCTION public.dincr_guard_financial_truncate()', 'trg_' || t || '_truncate_guard', t);
        EXECUTE format('CREATE OR REPLACE TRIGGER %I BEFORE UPDATE OF workspace_id ON public.%I '
                       'FOR EACH ROW EXECUTE FUNCTION public.dincr_guard_workspace_move()', 'trg_' || t || '_workspace_move_guard', t);
    END LOOP;
END $$;

-- Runtime access: exactly what the code runs (no DELETE: receipts are evidence).
GRANT SELECT, INSERT, UPDATE ON TABLE public.payroll_receipts TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.payroll_receipt_lines TO dincr_app;
GRANT USAGE ON SEQUENCE public.payroll_receipts_id_seq TO dincr_app;
GRANT USAGE ON SEQUENCE public.payroll_receipt_lines_id_seq TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.payroll_trusted_senders TO dincr_app;
GRANT USAGE ON SEQUENCE public.payroll_trusted_senders_id_seq TO dincr_app;
REVOKE ALL ON TABLE public.payroll_receipts, public.payroll_receipt_lines, public.payroll_trusted_senders FROM anon, authenticated;

ALTER TABLE public.payroll_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payroll_receipt_lines ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dincr_app_access ON public.payroll_receipts;
CREATE POLICY dincr_app_access ON public.payroll_receipts AS PERMISSIVE FOR ALL TO dincr_app USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS dincr_app_access ON public.payroll_receipt_lines;
CREATE POLICY dincr_app_access ON public.payroll_receipt_lines AS PERMISSIVE FOR ALL TO dincr_app USING (true) WITH CHECK (true);
ALTER TABLE public.payroll_trusted_senders ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dincr_app_access ON public.payroll_trusted_senders;
CREATE POLICY dincr_app_access ON public.payroll_trusted_senders AS PERMISSIVE FOR ALL TO dincr_app USING (true) WITH CHECK (true);

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'missing ' || t FROM unnest(ARRAY['payroll_receipts', 'payroll_receipt_lines', 'payroll_trusted_senders']) t WHERE to_regclass('public.' || t) IS NULL
-- UNION ALL SELECT 'dincr_app lacks ' || p || ' on payroll_receipts' FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE']) p
--   WHERE NOT has_table_privilege('dincr_app', 'public.payroll_receipts', p)
-- UNION ALL SELECT 'dincr_app lacks ' || p || ' on payroll_receipt_lines' FROM unnest(ARRAY['SELECT', 'INSERT']) p
--   WHERE NOT has_table_privilege('dincr_app', 'public.payroll_receipt_lines', p)
-- UNION ALL SELECT 'dincr_app lacks ' || p || ' on payroll_trusted_senders' FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE']) p
--   WHERE NOT has_table_privilege('dincr_app', 'public.payroll_trusted_senders', p)
-- UNION ALL SELECT 'dincr_app has extra DELETE on ' || t FROM unnest(ARRAY['payroll_receipts', 'payroll_receipt_lines', 'payroll_trusted_senders']) t
--   WHERE has_table_privilege('dincr_app', 'public.' || t, 'DELETE')
-- UNION ALL SELECT r || ' has access to ' || t FROM unnest(ARRAY['anon', 'authenticated']) r, unnest(ARRAY['payroll_receipts', 'payroll_receipt_lines', 'payroll_trusted_senders']) t
--   WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) AND has_table_privilege(r, 'public.' || t, 'SELECT')
-- UNION ALL SELECT 'missing guard on ' || t FROM unnest(ARRAY['payroll_receipts', 'payroll_receipt_lines', 'payroll_trusted_senders']) t
--   WHERE NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = ('public.' || t)::regclass AND tgname = 'trg_' || t || '_delete_guard')
-- UNION ALL SELECT 'RLS off on ' || t FROM unnest(ARRAY['payroll_receipts', 'payroll_receipt_lines', 'payroll_trusted_senders']) t
--   WHERE NOT (SELECT relrowsecurity FROM pg_class WHERE oid = ('public.' || t)::regclass);
