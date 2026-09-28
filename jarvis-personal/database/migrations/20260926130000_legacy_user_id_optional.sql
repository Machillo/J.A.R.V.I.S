-- Legacy identity retirement, phase E1: the legacy user_id becomes optional.
--
-- Ownership is workspace_id (NOT NULL, canonical) everywhere. A few legacy readers
-- still resolve identity through user_id (notification recipients, Owner memory);
-- they move to canonical ids in the next phase, before any writer stops writing
-- user_id. This migration only removes obligations, so current code keeps working:
--   1. Nine tables whose only deletion path was the legacy user_id cascade get a
--      workspace_id -> workspaces ON DELETE CASCADE foreign key (and an index on
--      workspace_id when none leads with it), so account deletion reaches them once
--      user_id is NULL. Aborts (LI001) on any row whose workspace does not exist.
--   2. Every public table with a user_id (from the catalog; audit_backup_* excluded)
--      must then have such a validated cascade, or the migration aborts (LI003): a
--      row without user_id must never survive the deletion of its workspace.
--   3. user_id loses its DEFAULT (1: a write that omitted it was silently attributed
--      to legacy id 1) and its NOT NULL. Each column that was NOT NULL is marked
--      with a column comment, so the rollback restores exactly those. The #245 guard
--      already treats a NULL user_id as the canonical state.
-- No row is updated or deleted; aborts change nothing. user_id columns and their
-- FKs stay until the retirement phase. Every target table is locked up front in
-- name order (fail fast on lock_timeout instead of deadlocking with the app).
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, in
-- a low-traffic window, before the code that stops writing user_id is deployed.
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
    targets TEXT[];
    uncovered TEXT[];
BEGIN
    SELECT array_agg(c.relname::TEXT ORDER BY c.relname) INTO targets
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'user_id' AND NOT a.attisdropped
    WHERE c.relkind IN ('r', 'p') AND c.relname NOT LIKE 'audit\_backup\_%';

    FOREACH t IN ARRAY COALESCE(targets, ARRAY[]::TEXT[]) LOOP
        EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', t);
    END LOOP;

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
        IF NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
                       WHERE i.indrelid = ('public.' || t)::regclass AND a.attname = 'workspace_id') THEN
            EXECUTE format('CREATE INDEX %I ON public.%I (workspace_id)', t || '_workspace_id_idx', t);
        END IF;
    END LOOP;

    SELECT array_agg(x ORDER BY x) INTO uncovered FROM unnest(COALESCE(targets, ARRAY[]::TEXT[])) x
    WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint k
        JOIN pg_attribute att ON att.attrelid = k.conrelid AND att.attnum = ANY(k.conkey)
        WHERE k.contype = 'f' AND k.conrelid = ('public.' || x)::regclass
          AND k.confrelid = 'public.workspaces'::regclass AND k.confdeltype = 'c'
          AND k.convalidated AND att.attname = 'workspace_id');
    IF uncovered IS NOT NULL THEN
        RAISE EXCEPTION 'tables without a workspace cascade: %; add it before making user_id optional', uncovered
            USING ERRCODE = 'LI003';
    END IF;

    FOREACH t IN ARRAY COALESCE(targets, ARRAY[]::TEXT[]) LOOP
        IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = ('public.' || t)::regclass
                   AND attname = 'user_id' AND attnotnull) THEN
            EXECUTE format('COMMENT ON COLUMN public.%I.user_id IS %L', t,
                           'legacy user_id; NOT NULL until 20260926130000');
        END IF;
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN user_id DROP DEFAULT, ALTER COLUMN user_id DROP NOT NULL', t);
    END LOOP;
END $$;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'user_id still required or defaulted on ' || c.relname FROM pg_class c
--  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
--  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'user_id' AND NOT a.attisdropped
--  WHERE c.relkind IN ('r', 'p') AND c.relname NOT LIKE 'audit\_backup\_%' AND (a.attnotnull OR a.atthasdef)
-- UNION ALL
-- SELECT 'no workspace cascade on ' || c.relname FROM pg_class c
--  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
--  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'user_id' AND NOT a.attisdropped
--  WHERE c.relkind IN ('r', 'p') AND c.relname NOT LIKE 'audit\_backup\_%' AND NOT EXISTS (
--    SELECT 1 FROM pg_constraint k JOIN pg_attribute att ON att.attrelid = k.conrelid AND att.attnum = ANY(k.conkey)
--    WHERE k.contype = 'f' AND k.conrelid = c.oid AND k.confrelid = 'public.workspaces'::regclass
--      AND k.confdeltype = 'c' AND k.convalidated AND att.attname = 'workspace_id');
