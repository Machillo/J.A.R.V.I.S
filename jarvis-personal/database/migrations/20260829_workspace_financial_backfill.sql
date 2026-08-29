-- JARVIS unified architecture - Phase 2A
-- Add workspace ownership to legacy Personal financial tables and backfill it safely.
-- NON-DESTRUCTIVE: does not drop columns/tables, does not remove user_id, and does not enforce NOT NULL yet.

DO $$
DECLARE
    tbl TEXT;
    target_tables TEXT[] := ARRAY[
        'events',
        'salaries',
        'bonuses',
        'debts',
        'debt_payments',
        'savings',
        'investments',
        'expenses',
        'employment_profile',
        'payroll_deductions',
        'payroll_events',
        'financial_goals',
        'payment_schedules',
        'pay_schedule',
        'credit_card_settings',
        'transactions',
        'exchange_rates',
        'receivables',
        'receivable_payments',
        'receivable_entries',
        'fixed_expenses',
        'fixed_expense_matches',
        'investment_cashflows',
        'investment_portfolio_snapshots',
        'business_projects',
        'business_movements'
    ];
    fk_name TEXT;
BEGIN
    FOREACH tbl IN ARRAY target_tables LOOP
        -- Some installations may not have every historical module yet.
        IF to_regclass(format('public.%I', tbl)) IS NULL THEN
            CONTINUE;
        END IF;

        -- Only migrate tables that still expose the legacy Personal user_id ownership column.
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns AS isc
            WHERE isc.table_schema = 'public'
              AND isc.table_name = tbl
              AND isc.column_name = 'user_id'
        ) THEN
            CONTINUE;
        END IF;

        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS workspace_id UUID', tbl);

        -- Exact mapping: legacy allowed_users.id -> accounts.legacy_allowed_user_id -> personal workspace.
        EXECUTE format($fmt$
            UPDATE public.%I AS legacy
               SET workspace_id = w.id
              FROM public.accounts a
              JOIN public.workspaces w
                ON w.owner_account_id = a.id
               AND w.workspace_type = 'personal'
             WHERE legacy.workspace_id IS NULL
               AND a.legacy_allowed_user_id = legacy.user_id
        $fmt$, tbl);

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON public.%I(workspace_id)',
            'idx_' || tbl || '_workspace_id',
            tbl
        );

        fk_name := 'fk_' || tbl || '_workspace';
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class r ON r.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = r.relnamespace
            WHERE c.conname = fk_name
              AND n.nspname = 'public'
              AND r.relname = tbl
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT NOT VALID',
                tbl,
                fk_name
            );
        END IF;
    END LOOP;
END $$;

-- Runtime audit: returns only tables that exist in this installation.
CREATE OR REPLACE FUNCTION public.jarvis_workspace_backfill_audit()
RETURNS TABLE (
    table_name TEXT,
    total_rows BIGINT,
    mapped_rows BIGINT,
    unmapped_rows BIGINT,
    distinct_workspaces BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    tbl TEXT;
    target_tables TEXT[] := ARRAY[
        'events',
        'salaries',
        'bonuses',
        'debts',
        'debt_payments',
        'savings',
        'investments',
        'expenses',
        'employment_profile',
        'payroll_deductions',
        'payroll_events',
        'financial_goals',
        'payment_schedules',
        'pay_schedule',
        'credit_card_settings',
        'transactions',
        'exchange_rates',
        'receivables',
        'receivable_payments',
        'receivable_entries',
        'fixed_expenses',
        'fixed_expense_matches',
        'investment_cashflows',
        'investment_portfolio_snapshots',
        'business_projects',
        'business_movements'
    ];
BEGIN
    FOREACH tbl IN ARRAY target_tables LOOP
        IF to_regclass(format('public.%I', tbl)) IS NULL THEN
            CONTINUE;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns AS isc
            WHERE isc.table_schema = 'public'
              AND isc.table_name = tbl
              AND isc.column_name = 'workspace_id'
        ) THEN
            CONTINUE;
        END IF;

        RETURN QUERY EXECUTE format(
            'SELECT %L::TEXT, COUNT(*)::BIGINT, COUNT(workspace_id)::BIGINT, COUNT(*) FILTER (WHERE workspace_id IS NULL)::BIGINT, COUNT(DISTINCT workspace_id)::BIGINT FROM public.%I',
            tbl,
            tbl
        );
    END LOOP;
END $$;

COMMENT ON FUNCTION public.jarvis_workspace_backfill_audit() IS
'Phase 2A migration audit. unmapped_rows must be zero before enforcing workspace ownership or switching backend reads/writes.';
