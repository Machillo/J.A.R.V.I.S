-- Internal functions are invoked only by migrations/backend triggers. They are
-- not part of the Supabase Data API.

BEGIN;

CREATE OR REPLACE FUNCTION public.jarvis_workspace_backfill_audit()
RETURNS TABLE (
    table_name TEXT,
    total_rows BIGINT,
    mapped_rows BIGINT,
    unmapped_rows BIGINT,
    distinct_workspaces BIGINT
)
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $function$
DECLARE
    tbl TEXT;
    target_tables TEXT[] := ARRAY[
        'events','salaries','bonuses','debts','debt_payments','savings','investments',
        'expenses','employment_profile','payroll_deductions','payroll_events',
        'financial_goals','payment_schedules','pay_schedule','credit_card_settings',
        'transactions','exchange_rates','receivables','receivable_payments',
        'receivable_entries','fixed_expenses','fixed_expense_matches','investment_cashflows',
        'investment_portfolio_snapshots','business_projects','business_movements'
    ];
BEGIN
    FOREACH tbl IN ARRAY target_tables LOOP
        IF pg_catalog.to_regclass(pg_catalog.format('public.%I', tbl)) IS NULL THEN
            CONTINUE;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns AS isc
            WHERE isc.table_schema='public' AND isc.table_name=tbl AND isc.column_name='workspace_id'
        ) THEN
            CONTINUE;
        END IF;
        RETURN QUERY EXECUTE pg_catalog.format(
            'SELECT %L::TEXT, COUNT(*)::BIGINT, COUNT(workspace_id)::BIGINT, COUNT(*) FILTER (WHERE workspace_id IS NULL)::BIGINT, COUNT(DISTINCT workspace_id)::BIGINT FROM public.%I',
            tbl, tbl
        );
    END LOOP;
END
$function$;

CREATE OR REPLACE FUNCTION public.jarvis_link_financial_account()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF NEW.financial_account_id IS NULL AND NULLIF(pg_catalog.btrim(NEW.account),'') IS NOT NULL THEN
        SELECT account_row.id INTO NEW.financial_account_id
        FROM public.account_balances AS account_row
        WHERE account_row.workspace_id=NEW.workspace_id
          AND account_row.is_active=TRUE
          AND (
              pg_catalog.lower(pg_catalog.btrim(account_row.account_name))=pg_catalog.lower(pg_catalog.btrim(NEW.account))
              OR (account_row.account_last4<>'' AND NEW.account LIKE pg_catalog.chr(37) || account_row.account_last4)
          )
        ORDER BY CASE
            WHEN pg_catalog.lower(pg_catalog.btrim(account_row.account_name))=pg_catalog.lower(pg_catalog.btrim(NEW.account)) THEN 0
            ELSE 1
        END, account_row.id
        LIMIT 1;
    END IF;
    RETURN NEW;
END
$function$;

REVOKE ALL ON FUNCTION public.jarvis_workspace_backfill_audit() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.jarvis_link_financial_account() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.jarvis_workspace_backfill_audit() TO postgres;
GRANT EXECUTE ON FUNCTION public.jarvis_link_financial_account() TO postgres;

-- PostgreSQL grants EXECUTE on new functions to PUBLIC unless changed. Apply
-- this to functions created in public by the migration/database owner.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

COMMIT;
