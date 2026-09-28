-- Rollback of 20260926131000_workspace_unique_keys.sql: drops only the four
-- workspace-scoped unique indexes it created. Safe only while every writer still
-- writes user_id (the user_id indexes then keep deduplicating on their own).
-- BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DROP INDEX IF EXISTS public.uq_credit_card_settings_workspace_bank_card;
DROP INDEX IF EXISTS public.uq_debt_payments_workspace_monthly_due;
DROP INDEX IF EXISTS public.uq_fixed_expense_matches_workspace_period;
DROP INDEX IF EXISTS public.uq_fixed_expenses_workspace_name;

COMMIT;
