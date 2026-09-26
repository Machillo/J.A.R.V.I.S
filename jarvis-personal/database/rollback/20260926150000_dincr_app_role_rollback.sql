-- Rollback of 20260926150000: removes the dedicated application role.
--
-- PRE-ROLLBACK GATE: no process connects as dincr_app any more (the backend is
-- back on its previous DATABASE_URL). Restores the #245 delete guard, drops the
-- dincr_app_access policies and every privilege of the role, then the role.
-- Leaves the mail secret boundary (20260926149000) in place.
-- BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

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

    -- Every session other than the application (application_name 'dincr-backend',
    -- or 'Supavisor' when the pooler reports its own name) must declare the one
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
    IF COALESCE(current_setting('application_name', true), '') NOT IN ('Supavisor', 'dincr-backend') THEN
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

DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT tablename FROM pg_policies WHERE schemaname = 'public' AND policyname = 'dincr_app_access' LOOP
        EXECUTE format('DROP POLICY dincr_app_access ON public.%I', t);
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        -- Explicit revokes: DROP OWNED BY needs the role's own privileges, which a
        -- non-superuser migrator (Supabase's postgres) does not have. dincr_app owns
        -- nothing (checked by the migration postflight).
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM dincr_app;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM dincr_app;
        REVOKE ALL ON SCHEMA public FROM dincr_app;
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'dincr_private') THEN
            REVOKE ALL ON ALL FUNCTIONS IN SCHEMA dincr_private FROM dincr_app;
            REVOKE ALL ON SCHEMA dincr_private FROM dincr_app;
        END IF;
        DROP ROLE dincr_app;
    END IF;
END $$;

COMMIT;
