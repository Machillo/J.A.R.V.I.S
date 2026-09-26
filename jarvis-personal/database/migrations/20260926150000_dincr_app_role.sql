-- Dedicated application database role (dincr_app), least privilege.
--
-- The backend connects today as the privileged table owner. This migration creates
-- the role it will connect as instead. The switch itself is a human step (password
-- and pooler connection string, see docs/security/database-role.md); until then
-- nothing changes for the running backend.
--
-- dincr_app:
-- - LOGIN, NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS, no
--   password here (set by a human), idle-in-transaction sessions ended after 60s;
-- - owns nothing and has no DDL: USAGE (not CREATE) on schema public; aborts
--   (APP01) if PUBLIC would give it CREATE there;
-- - explicit per-table privileges, derived from the SQL the backend runs
--   (backend/tests/test_dincr_app_grants.py keeps them in step with the code);
--   USAGE only on the sequences owned by the tables it inserts into;
-- - row level security stays on for every table; the role gets one explicit
--   permissive policy per granted table (dincr_app_access). Workspace-scoped
--   policies replace it in the strict RLS change (design in the same doc);
-- - no access to auth, storage or vault; EXECUTE on the mail secret boundary
--   functions (20260926149000) only;
-- - the financial delete guard (#245) recognises the application by
--   session_user = 'dincr_app'; the old application_name rule is still accepted
--   until 20260926151000.
-- Requires 20260926125000 (Owner legacy schema) and 20260926149000 (mail secret
-- boundary) first: aborts (APP03) if a granted table is missing. Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED)
-- as postgres, BEFORE the code of this PR is deployed (the code calls the
-- dincr_private functions). The running backend keeps its current role until the
-- human switch; this migration changes nothing for it except the guard, which
-- still accepts it.
--
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926150000_dincr_app_role_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

-- CREATE ROLE's defaults are NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
-- NOBYPASSRLS; a non-superuser migrator (Supabase's postgres) may not even name the
-- superuser-only attributes, so they are verified instead of altered.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        CREATE ROLE dincr_app LOGIN NOINHERIT;
    ELSE
        ALTER ROLE dincr_app LOGIN NOINHERIT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app'
               AND (rolsuper OR rolreplication OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolinherit)) THEN
        RAISE EXCEPTION 'dincr_app has a privileged attribute; a superuser must remove it first' USING ERRCODE = 'APP01';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = 'dincr_app'::regrole) THEN
        RAISE EXCEPTION 'dincr_app is a member of another role; remove the membership first' USING ERRCODE = 'APP01';
    END IF;
END $$;

ALTER ROLE dincr_app SET idle_in_transaction_session_timeout = '60s';

REVOKE ALL ON SCHEMA public FROM dincr_app;
GRANT USAGE ON SCHEMA public TO dincr_app;
DO $$
BEGIN
    IF has_schema_privilege('dincr_app', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'dincr_app could create objects in schema public (granted to PUBLIC?); decide before applying'
            USING ERRCODE = 'APP01';
    END IF;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM dincr_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM dincr_app;

DO $$
DECLARE
    missing TEXT[];
BEGIN
    SELECT array_agg(t ORDER BY t) INTO missing FROM unnest(ARRAY[
        'account_balance_history', 'account_balances', 'account_subscriptions', 'accounts', 'advisor_current_strategy',
        'advisor_strategy_history', 'allowed_users', 'app_feature_flag_audit', 'app_feature_flags', 'app_release_policies',
        'billing_orders', 'billing_subscriptions', 'bonuses', 'business_movements', 'business_projects',
        'card_aliases', 'category_catalog', 'chat_pending_actions', 'chat_sessions', 'credit_card_settings',
        'debt_payments', 'debts', 'deployment_events', 'email_classification_rules', 'email_financial_accounts',
        'email_ingested_messages', 'email_monitor_settings', 'email_parser_logs', 'email_statement_documents', 'email_statement_reconciliation_lines',
        'email_transaction_candidates', 'employment_profile', 'events', 'exchange_rates', 'expenses',
        'features', 'feedback_reports', 'financial_goals', 'financial_health_snapshots', 'financial_input_events',
        'financial_profiles', 'financial_state_snapshots', 'finva_budget_items', 'finva_email_candidates', 'finva_email_messages',
        'finva_gmail_connections', 'finva_gmail_consents', 'finva_goal_contributions', 'finva_recurring_items', 'finva_savings_plan_contributions',
        'finva_savings_plans', 'finva_statement_documents', 'fixed_expenses', 'investment_cashflows',
        'investment_portfolio_snapshots', 'investment_position_snapshots', 'investments', 'legal_acceptances', 'logs',
        'mail_oauth_flows', 'memory_items', 'net_worth_snapshots', 'notification_jobs', 'notification_subscriptions',
        'operation_idempotency', 'pay_schedule', 'payment_schedules', 'payroll_deductions', 'payroll_events',
        'payroll_salary_reports', 'plan_features', 'plans', 'product_events', 'receivable_entries',
        'receivable_payments', 'receivables', 'salaries', 'savings', 'settings',
        'store_subscription_events', 'store_subscriptions', 'transactions', 'user_preferences', 'users',
        'workspace_members', 'workspaces']) t
    WHERE to_regclass('public.' || t) IS NULL;
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'tables missing (apply 20260926125000 first): %', missing USING ERRCODE = 'APP03';
    END IF;
END $$;

GRANT SELECT, INSERT ON TABLE public.account_balance_history TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.account_balances TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.account_subscriptions TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.accounts TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.advisor_current_strategy TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.advisor_strategy_history TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.allowed_users TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.app_feature_flag_audit TO dincr_app;
GRANT SELECT, UPDATE ON TABLE public.app_feature_flags TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.app_release_policies TO dincr_app;
GRANT SELECT, UPDATE ON TABLE public.billing_orders TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.billing_subscriptions TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.bonuses TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.business_movements TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.business_projects TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.card_aliases TO dincr_app;
GRANT SELECT ON TABLE public.category_catalog TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.chat_pending_actions TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.chat_sessions TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.credit_card_settings TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.debt_payments TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.debts TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.deployment_events TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.email_classification_rules TO dincr_app;
GRANT SELECT ON TABLE public.email_financial_accounts TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.email_ingested_messages TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.email_monitor_settings TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.email_parser_logs TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.email_statement_documents TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.email_statement_reconciliation_lines TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.email_transaction_candidates TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.employment_profile TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.events TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.exchange_rates TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.expenses TO dincr_app;
GRANT SELECT ON TABLE public.features TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.feedback_reports TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.financial_goals TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.financial_health_snapshots TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.financial_input_events TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.financial_profiles TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.financial_state_snapshots TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.finva_budget_items TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.finva_email_candidates TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.finva_email_messages TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.finva_gmail_connections TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.finva_gmail_consents TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.finva_goal_contributions TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.finva_recurring_items TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.finva_savings_plan_contributions TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.finva_savings_plans TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.finva_statement_documents TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.fixed_expenses TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.investment_cashflows TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.investment_portfolio_snapshots TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.investment_position_snapshots TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.investments TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.legal_acceptances TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.logs TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.mail_oauth_flows TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.memory_items TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.net_worth_snapshots TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.notification_jobs TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.notification_subscriptions TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.operation_idempotency TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.pay_schedule TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.payment_schedules TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.payroll_deductions TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.payroll_events TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.payroll_salary_reports TO dincr_app;
GRANT SELECT ON TABLE public.plan_features TO dincr_app;
GRANT SELECT ON TABLE public.plans TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.product_events TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.receivable_entries TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.receivable_payments TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.receivables TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.salaries TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.savings TO dincr_app;
GRANT SELECT ON TABLE public.settings TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.store_subscription_events TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.store_subscriptions TO dincr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.transactions TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.user_preferences TO dincr_app;
GRANT SELECT, INSERT, DELETE ON TABLE public.users TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.workspace_members TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.workspaces TO dincr_app;

-- Sequences owned by the tables the application inserts into: USAGE only (nextval),
-- never SELECT/UPDATE (setval).
DO $$
DECLARE
    s TEXT;
BEGIN
    FOR s IN
        SELECT DISTINCT format('%I.%I', sn.nspname, sc.relname)
        FROM pg_depend d
        JOIN pg_class sc ON sc.oid = d.objid AND sc.relkind = 'S'
        JOIN pg_namespace sn ON sn.oid = sc.relnamespace
        JOIN pg_class tc ON tc.oid = d.refobjid
        JOIN pg_namespace tn ON tn.oid = tc.relnamespace AND tn.nspname = 'public'
        WHERE d.classid = 'pg_class'::regclass AND d.refclassid = 'pg_class'::regclass
          AND d.deptype IN ('a', 'i')
          AND tc.relname = ANY(ARRAY[
        'account_balance_history', 'account_balances', 'account_subscriptions', 'accounts', 'advisor_current_strategy',
        'advisor_strategy_history', 'allowed_users', 'app_feature_flag_audit', 'app_release_policies', 'billing_subscriptions',
        'bonuses', 'business_movements', 'business_projects', 'card_aliases', 'chat_pending_actions',
        'chat_sessions', 'credit_card_settings', 'debt_payments', 'debts', 'deployment_events',
        'email_classification_rules', 'email_ingested_messages', 'email_monitor_settings', 'email_parser_logs', 'email_statement_documents',
        'email_statement_reconciliation_lines', 'email_transaction_candidates', 'employment_profile', 'events', 'exchange_rates',
        'expenses', 'feedback_reports', 'financial_goals', 'financial_health_snapshots', 'financial_input_events',
        'financial_profiles', 'financial_state_snapshots', 'finva_budget_items', 'finva_email_candidates', 'finva_email_messages',
        'finva_gmail_connections', 'finva_gmail_consents', 'finva_goal_contributions', 'finva_recurring_items', 'finva_savings_plan_contributions',
        'finva_savings_plans', 'finva_statement_documents', 'fixed_expenses', 'investment_cashflows', 'investment_portfolio_snapshots',
        'investment_position_snapshots', 'investments', 'legal_acceptances', 'logs', 'mail_oauth_flows',
        'memory_items', 'net_worth_snapshots', 'notification_jobs', 'notification_subscriptions', 'operation_idempotency',
        'pay_schedule', 'payment_schedules', 'payroll_deductions', 'payroll_events', 'payroll_salary_reports',
        'product_events', 'receivable_entries', 'receivable_payments', 'receivables', 'salaries',
        'savings', 'store_subscription_events', 'store_subscriptions', 'transactions', 'user_preferences',
        'users', 'workspace_members', 'workspaces'])
    LOOP
        EXECUTE format('GRANT USAGE ON SEQUENCE %s TO dincr_app', s);
    END LOOP;
END $$;

-- Privileges that follow the catalog rather than a list:
-- - account deletion deletes, by dynamic SQL, from every table with a foreign key to
--   allowed_users (backend/auth/service.py::_delete_allowed_user_dependents);
-- - the personal data export reads every table with account_id or workspace_id
--   (backend/auth/data_export.py); a table it cannot read would silently be missing.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT DISTINCT child.relname FROM pg_constraint c
        JOIN pg_class child ON child.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = child.relnamespace AND n.nspname = 'public'
        WHERE c.contype = 'f' AND c.confrelid = 'public.allowed_users'::regclass
          AND array_length(c.conkey, 1) = 1 AND c.conrelid <> c.confrelid AND c.confdeltype IN ('a', 'r', 'c')
    LOOP
        EXECUTE format('GRANT SELECT, DELETE ON TABLE public.%I TO dincr_app', t);
    END LOOP;
    FOR t IN
        SELECT DISTINCT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname IN ('account_id', 'workspace_id') AND NOT a.attisdropped
        WHERE c.relkind IN ('r', 'p')
    LOOP
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO dincr_app', t);
    END LOOP;
END $$;

-- Row level security stays on for every table the role can reach, with one explicit
-- policy each (without it the role would silently read no rows). Workspace-scoped
-- policies replace it in the strict RLS change.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        WHERE c.relkind IN ('r', 'p') AND has_table_privilege('dincr_app', c.oid, 'SELECT')
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = t
                       AND policyname = 'dincr_app_access') THEN
            EXECUTE format('CREATE POLICY dincr_app_access ON public.%I AS PERMISSIVE FOR ALL TO dincr_app
                            USING (true) WITH CHECK (true)', t);
        END IF;
    END LOOP;
END $$;

-- Mail refresh tokens: only through the dincr_private boundary (20260926149000).
GRANT USAGE ON SCHEMA dincr_private TO dincr_app;
GRANT EXECUTE ON FUNCTION dincr_private.mail_secret_create(TEXT, UUID, TEXT) TO dincr_app;
GRANT EXECUTE ON FUNCTION dincr_private.mail_secret_read(UUID, UUID) TO dincr_app;
GRANT EXECUTE ON FUNCTION dincr_private.mail_secret_delete(UUID[], UUID) TO dincr_app;

-- #245 delete guard: the application is its login role.
CREATE OR REPLACE FUNCTION public.dincr_guard_financial_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_owners BIGINT;
    v_declared TEXT := NULLIF(current_setting('dincr.delete_workspace', true), '');
    v_outside BIGINT;
BEGIN
    -- Identifiers of live workspaces only: rows of a workspace that no longer
    -- exists (account deletion) are logged as a count.
    INSERT INTO public.financial_ownership_delete_log(
        table_name, row_count, row_ids, workspace_ids, db_role,
        application_name, transaction_id)
    SELECT TG_TABLE_NAME, COUNT(*),
           -- Ids of live-workspace rows and of rows without a workspace (the ones
           -- whose owner is unclear); a deleted workspace's cascade is a count.
           COALESCE(array_agg(r.row_id ORDER BY r.row_id) FILTER (WHERE r.row_id IS NOT NULL AND (w.id IS NOT NULL OR o.workspace_id IS NULL)), ARRAY[]::BIGINT[]),
           COALESCE(array_agg(DISTINCT o.workspace_id) FILTER (WHERE w.id IS NOT NULL), ARRAY[]::UUID[]),
           session_user::TEXT,
           NULLIF(current_setting('application_name', true), ''), txid_current()
    FROM old_rows o
    -- Tables keyed by something other than an integer id log counts only.
    CROSS JOIN LATERAL (SELECT pg_catalog.to_jsonb(o) ->> 'id' AS raw_id) j
    CROSS JOIN LATERAL (SELECT CASE WHEN j.raw_id ~ '^-?[0-9]{1,18}$' THEN j.raw_id::BIGINT END AS row_id) r
    LEFT JOIN public.workspaces w ON w.id = o.workspace_id
    HAVING COUNT(*) > 0;

    SELECT COUNT(DISTINCT w.owner_account_id) INTO v_owners
    FROM old_rows o
    JOIN public.workspaces w ON w.id = o.workspace_id;
    IF v_owners > 1 THEN
        -- No identifiers or values in the message: it can reach logs.
        RAISE EXCEPTION 'financial delete on % spans % live owners', TG_TABLE_NAME, v_owners
            USING ERRCODE = '23514',
                  HINT = 'delete one account''s rows per statement; never select financial rows by legacy user_id';
    END IF;

    -- Rows without a workspace have no clear owner: every session, the app
    -- included, deletes them only with the explicit declaration 'none'. The app
    -- declares it only for an identity's own FK cascade: in account deletion and
    -- when an admin deletes an allowed_users row that no account maps to; the
    -- NOT VALID CHECK keeps new ones from appearing.
    IF v_declared IS DISTINCT FROM 'none' AND EXISTS (SELECT 1 FROM old_rows o WHERE o.workspace_id IS NULL) THEN
        RAISE EXCEPTION 'financial delete on % touches rows without a workspace', TG_TABLE_NAME
            USING ERRCODE = '23514',
                  HINT = 'SET LOCAL dincr.delete_workspace = ''none'' to delete rows without a workspace';
    END IF;

    -- Every session other than the application must declare the one
    -- workspace it deletes from: SET LOCAL dincr.delete_workspace = '<uuid>'.
    -- Use SET LOCAL: a session-level SET is also honoured and would cover later
    -- deletes in the same session. This covers the SQL editor, psql, scripts, the
    -- CLI and agents.
    -- PRE-APPLY GATE: every process that deletes on behalf of the app must be
    -- the web app (backend/main.py sets 'dincr-backend') or connect through the
    -- pooler ('Supavisor'); any other process must declare its workspace or
    -- its deletes of live rows are rejected here (fail closed). Scripts using
    -- backend.core.database identify as 'dincr-script' and must declare.
    -- Rows without a workspace belong to no declared workspace: deleting them
    -- takes the explicit declaration 'none'. Rows of a workspace deleted in the
    -- same statement (a manual account deletion) need that workspace declared.
    -- The application is identified by its login role (session_user, which a client
    -- cannot change), not by application_name. Until the backend connects as
    -- dincr_app, the previous application_name rule is still accepted; migration
    -- 20260926151000 removes it once the switch is verified.
    IF session_user::TEXT <> 'dincr_app'
       AND COALESCE(current_setting('application_name', true), '') NOT IN ('Supavisor', 'dincr-backend') THEN
        SELECT COUNT(*) INTO v_outside
        FROM old_rows o
        WHERE o.workspace_id IS NOT NULL AND (v_declared IS NULL OR o.workspace_id::TEXT <> v_declared);
        IF v_outside > 0 THEN
            RAISE EXCEPTION 'manual financial delete on % touches % rows outside the declared workspace', TG_TABLE_NAME, v_outside
                USING ERRCODE = '23514',
                      HINT = 'SET LOCAL dincr.delete_workspace to the one workspace being cleaned up';
        END IF;
    END IF;
    RETURN NULL;
END
$fn$;
REVOKE ALL ON FUNCTION public.dincr_guard_financial_delete() FROM PUBLIC, anon, authenticated;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'role attribute' FROM pg_roles WHERE rolname = 'dincr_app'
--   AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR NOT rolcanlogin)
-- UNION ALL SELECT 'owns ' || c.relname FROM pg_class c WHERE c.relowner = 'dincr_app'::regrole
-- UNION ALL SELECT 'can create in public' WHERE has_schema_privilege('dincr_app', 'public', 'CREATE')
-- UNION ALL SELECT 'reads ' || x FROM unnest(ARRAY['vault.secrets', 'vault.decrypted_secrets', 'auth.users', 'storage.objects']) x
--   WHERE CASE WHEN to_regclass(x) IS NOT NULL THEN has_table_privilege('dincr_app', x, 'SELECT') ELSE false END
-- UNION ALL SELECT 'uses schema ' || s FROM unnest(ARRAY['vault', 'auth', 'storage']) s
--   WHERE CASE WHEN EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s)
--              THEN has_schema_privilege('dincr_app', s, 'USAGE') ELSE false END
-- UNION ALL SELECT 'setval on ' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--   WHERE n.nspname = 'public' AND CASE WHEN c.relkind = 'S' THEN has_sequence_privilege('dincr_app', c.oid, 'UPDATE') ELSE false END
-- UNION ALL SELECT 'public may run ' || p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--   WHERE n.nspname = 'dincr_private' AND has_function_privilege('public', p.oid, 'EXECUTE')
-- UNION ALL SELECT 'can create in the database' WHERE has_database_privilege('dincr_app', current_database(), 'CREATE')
-- UNION ALL SELECT 'uses schema ' || nspname FROM pg_namespace
--   WHERE nspname NOT IN ('public', 'dincr_private', 'pg_catalog', 'information_schema') AND nspname NOT LIKE 'pg\_%'
--     AND has_schema_privilege('dincr_app', oid, 'USAGE')
-- UNION ALL SELECT 'cannot delete from allowed_users dependent ' || c.conrelid::regclass FROM pg_constraint c
--   WHERE c.contype = 'f' AND c.confrelid = 'public.allowed_users'::regclass AND array_length(c.conkey, 1) = 1
--     AND c.conrelid <> c.confrelid AND c.confdeltype IN ('a', 'r', 'c')
--     AND NOT has_table_privilege('dincr_app', c.conrelid, 'DELETE')
-- UNION ALL SELECT 'cannot export ' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
--   WHERE c.relkind IN ('r', 'p') AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid
--     AND a.attname IN ('account_id', 'workspace_id') AND NOT a.attisdropped)
--     AND NOT has_table_privilege('dincr_app', c.oid, 'SELECT')
-- UNION ALL SELECT 'no policy on ' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
--   WHERE CASE WHEN c.relkind = 'r' THEN has_table_privilege('dincr_app', c.oid, 'SELECT') ELSE false END
--     AND NOT EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname
--                     AND 'dincr_app' = ANY(p.roles));
