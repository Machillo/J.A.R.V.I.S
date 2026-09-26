-- Legacy identity retirement, phase E1: the legacy user_id becomes optional.
--
-- Ownership is workspace_id (NOT NULL, canonical) everywhere. A few legacy readers
-- still resolve identity through user_id (notification recipients, Owner memory);
-- they move to canonical ids in the next phase, before any writer stops writing
-- user_id. This migration only removes obligations, so current code keeps working:
--   1. Nine tables whose only deletion path was the legacy user_id cascade get a
--      workspace_id -> workspaces ON DELETE CASCADE foreign key, so account
--      deletion reaches them once user_id is NULL. Aborts (LI001) on any row whose
--      workspace does not exist, changing nothing.
--   2. user_id loses its DEFAULT 1 (a write that omitted it was silently
--      attributed to legacy id 1) and its NOT NULL. The #245 guard already treats a
--      NULL user_id as the canonical state (dincr_guard_financial_ownership).
-- No row is updated or deleted. user_id columns and their FKs stay until phase F.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, at
-- any time before the code that stops writing user_id is deployed.
--
-- Preflight (read-only): must return zero rows.
--   SELECT t FROM unnest(ARRAY['ai_premium_guides','ai_premium_settings','ai_premium_usage_events','ai_usage_daily',
--     'ai_usage_events','email_classification_rules','email_financial_accounts',
--     'email_statement_reconciliation_lines','notification_jobs']) t
--   WHERE to_regclass('public.'||t) IS NOT NULL AND (xpath('/row/n/text()', query_to_xml(format(
--     'SELECT count(*) AS n FROM public.%I x WHERE NOT EXISTS (SELECT 1 FROM public.workspaces w WHERE w.id=x.workspace_id)', t),
--     false, true, '')))[1]::text::int > 0;
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926130000_legacy_user_id_optional_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $$
DECLARE
    t TEXT;
    orphans BIGINT;
BEGIN
    FOREACH t IN ARRAY ARRAY['ai_premium_guides','ai_premium_settings','ai_premium_usage_events','ai_usage_daily',
        'ai_usage_events','email_classification_rules','email_financial_accounts',
        'email_statement_reconciliation_lines','notification_jobs']
    LOOP
        CONTINUE WHEN to_regclass('public.' || t) IS NULL;
        EXECUTE format('LOCK TABLE public.%I IN SHARE ROW EXCLUSIVE MODE', t);
        EXECUTE format('SELECT count(*) FROM public.%I x WHERE x.workspace_id IS NULL
                        OR NOT EXISTS (SELECT 1 FROM public.workspaces w WHERE w.id = x.workspace_id)', t) INTO orphans;
        IF orphans > 0 THEN
            RAISE EXCEPTION 'table % has % rows without an existing workspace; resolve them first', t, orphans
                USING ERRCODE = 'LI001';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = t || '_workspace_fk'
                       AND conrelid = ('public.' || t)::regclass) THEN
            EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (workspace_id)
                            REFERENCES public.workspaces(id) ON DELETE CASCADE', t, t || '_workspace_fk');
        END IF;
    END LOOP;

    FOREACH t IN ARRAY ARRAY['account_balance_history','account_balances','ai_premium_guides','ai_premium_settings',
        'ai_premium_usage_events','ai_usage_daily','ai_usage_events','bonuses','business_movements','business_projects',
        'card_aliases','chat_pending_actions','chat_sessions','credit_card_settings','debt_payments','debts',
        'email_classification_rules','email_financial_accounts','email_ingested_messages','email_monitor_settings',
        'email_parser_logs','email_statement_documents','email_statement_reconciliation_lines',
        'email_transaction_candidates','employment_profile','events','exchange_rates','expenses','financial_goals',
        'financial_input_events','fixed_expense_matches','fixed_expenses','investment_cashflows',
        'investment_portfolio_snapshots','investments','logs','memory_items','net_worth_snapshots','notification_jobs',
        'notification_subscriptions','pay_schedule','payment_schedules','payroll_deductions','payroll_events',
        'payroll_salary_reports','receivable_entries','receivable_payments','receivables','salaries','savings',
        'transactions','user_preferences','goals','goal_schedules','investment_position_snapshots']
    LOOP
        CONTINUE WHEN to_regclass('public.' || t) IS NULL
            OR NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_schema = 'public' AND table_name = t AND column_name = 'user_id');
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN user_id DROP DEFAULT, ALTER COLUMN user_id DROP NOT NULL', t);
    END LOOP;
END $$;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'user_id still required or defaulted on ' || c.table_name FROM information_schema.columns c
--  JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'
--  WHERE c.table_schema = 'public' AND c.column_name = 'user_id' AND (c.is_nullable = 'NO' OR c.column_default IS NOT NULL)
-- UNION ALL
-- SELECT 'missing workspace FK on ' || t FROM unnest(ARRAY['ai_premium_guides','ai_premium_settings','ai_premium_usage_events',
--   'ai_usage_daily','ai_usage_events','email_classification_rules','email_financial_accounts',
--   'email_statement_reconciliation_lines','notification_jobs']) t
--  WHERE to_regclass('public.'||t) IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pg_constraint
--    WHERE conname = t || '_workspace_fk' AND conrelid = ('public.'||t)::regclass AND convalidated);
