-- Rollback of 20260926130000_legacy_user_id_optional.sql, only while no row has a
-- NULL user_id (i.e. before code that stops writing it has run). Aborts (LI002)
-- otherwise: re-requiring the column would need an ownership decision per row,
-- which is never automatic. DEFAULT 1 is deliberately NOT restored (it silently
-- attributed rows to legacy id 1). Drops only the workspace FKs this migration added.
-- BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    t TEXT;
    nulls BIGINT;
BEGIN
    FOR t IN
        SELECT c.table_name FROM information_schema.columns c
        JOIN information_schema.tables tb ON tb.table_schema = c.table_schema AND tb.table_name = c.table_name
                                          AND tb.table_type = 'BASE TABLE'
        WHERE c.table_schema = 'public' AND c.column_name = 'user_id' AND c.table_name NOT LIKE 'audit_backup_%'
    LOOP
        EXECUTE format('SELECT count(*) FROM public.%I WHERE user_id IS NULL', t) INTO nulls;
        IF nulls > 0 THEN
            RAISE EXCEPTION 'table % already has % rows without a legacy user_id; rollback is not automatic', t, nulls
                USING ERRCODE = 'LI002';
        END IF;
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN user_id SET NOT NULL', t);
    END LOOP;
    FOREACH t IN ARRAY ARRAY['ai_premium_guides','ai_premium_settings','ai_premium_usage_events','ai_usage_daily',
        'ai_usage_events','email_classification_rules','email_financial_accounts',
        'email_statement_reconciliation_lines','notification_jobs']
    LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', t, t || '_workspace_fk');
        END IF;
    END LOOP;
END $$;

COMMIT;
