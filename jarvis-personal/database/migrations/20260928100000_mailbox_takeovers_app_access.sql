-- Mailbox takeover audit: runtime access for the application role (dincr_app).
--
-- 20260926110000_mailbox_single_owner created public.mail_connection_takeovers, which
-- the mailbox claim (backend/user_product/mail_oauth.py claim_mailbox) writes when it
-- takes over a stale connection. The role migration (20260926150000) grants dincr_app
-- an explicit list of tables that does not include it, and its catalog rules do not
-- reach it (no account_id/workspace_id column, no allowed_users FK). Without this file
-- a takeover fails with "permission denied" under dincr_app. It gives dincr_app exactly
-- what that code runs, and nothing else:
-- - mail_connection_takeovers: SELECT, INSERT (the audit row), and USAGE on its id
--   sequence. No UPDATE or DELETE: the audit is append-only for the application;
-- - one dincr_app_access policy (RLS is on; without a policy the role writes no rows).
-- No table or column is created here (that is 110000's), and anon/authenticated get nothing.
--
-- PRE-APPLY GATE: 20260926110000 and 20260926150000 applied. Aborts otherwise
-- (MB003 / MB002) and changes nothing.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, BEFORE
-- the code that claims mailboxes (PR #249) is deployed.
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260928100000_mailbox_takeovers_app_access_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RAISE EXCEPTION 'role dincr_app is missing: apply 20260926150000 first' USING ERRCODE = 'MB002';
    END IF;
    IF to_regclass('public.mail_connection_takeovers') IS NULL
       OR to_regclass('public.mail_connection_takeovers_id_seq') IS NULL THEN
        RAISE EXCEPTION 'mailbox takeover audit is missing: apply 20260926110000 first' USING ERRCODE = 'MB003';
    END IF;
END $$;

GRANT SELECT, INSERT ON TABLE public.mail_connection_takeovers TO dincr_app;
GRANT USAGE ON SEQUENCE public.mail_connection_takeovers_id_seq TO dincr_app;

ALTER TABLE public.mail_connection_takeovers ENABLE ROW LEVEL SECURITY;
-- Re-created on every run, so a re-run leaves exactly this policy.
DROP POLICY IF EXISTS dincr_app_access ON public.mail_connection_takeovers;
CREATE POLICY dincr_app_access ON public.mail_connection_takeovers AS PERMISSIVE FOR ALL TO dincr_app
    USING (true) WITH CHECK (true);

COMMIT;

-- Postflight (read-only): must return zero rows.
-- WITH expected(p) AS (VALUES ('SELECT'), ('INSERT')),
-- actual(r, p) AS (
--     SELECT r, p
--     FROM unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r,
--          unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER']) p
--     WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
--       AND has_table_privilege(r, 'public.mail_connection_takeovers', p))
-- SELECT 'dincr_app lacks ' || p || ' on mail_connection_takeovers' FROM expected
--   WHERE ('dincr_app', p) NOT IN (SELECT r, p FROM actual)
-- UNION ALL SELECT r || ' has extra ' || p || ' on mail_connection_takeovers' FROM actual
--   WHERE NOT (r = 'dincr_app' AND p IN (SELECT p FROM expected))
-- UNION ALL SELECT 'dincr_app lacks USAGE on mail_connection_takeovers_id_seq'
--   WHERE NOT has_sequence_privilege('dincr_app', 'public.mail_connection_takeovers_id_seq', 'USAGE')
-- UNION ALL SELECT r || ' has ' || p || ' on mail_connection_takeovers_id_seq'
--   FROM unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r, unnest(ARRAY['SELECT', 'UPDATE']) p
--   WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
--     AND has_sequence_privilege(r, 'public.mail_connection_takeovers_id_seq', p)
-- UNION ALL SELECT r || ' has USAGE on mail_connection_takeovers_id_seq'
--   FROM unnest(ARRAY['anon', 'authenticated']) r
--   WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
--     AND has_sequence_privilege(r, 'public.mail_connection_takeovers_id_seq', 'USAGE')
-- UNION ALL SELECT 'row level security off on mail_connection_takeovers' FROM pg_class
--   WHERE oid = 'public.mail_connection_takeovers'::regclass AND NOT relrowsecurity
-- UNION ALL SELECT 'missing policy dincr_app_access on mail_connection_takeovers'
--   WHERE NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'mail_connection_takeovers'
--                     AND policyname = 'dincr_app_access')
-- UNION ALL SELECT 'wrong policy dincr_app_access on mail_connection_takeovers: ' || concat_ws(', ',
--          CASE WHEN permissive IS DISTINCT FROM 'PERMISSIVE' THEN 'not permissive' END,
--          CASE WHEN roles IS DISTINCT FROM ARRAY['dincr_app']::name[] THEN 'roles ' || roles::text END,
--          CASE WHEN cmd IS DISTINCT FROM 'ALL' THEN 'command ' || cmd END,
--          CASE WHEN qual IS DISTINCT FROM 'true' THEN 'USING ' || coalesce(qual, 'none') END,
--          CASE WHEN with_check IS DISTINCT FROM 'true' THEN 'WITH CHECK ' || coalesce(with_check, 'none') END)
--   FROM pg_policies
--   WHERE schemaname = 'public' AND policyname = 'dincr_app_access' AND tablename = 'mail_connection_takeovers'
--     AND (permissive IS DISTINCT FROM 'PERMISSIVE' OR roles IS DISTINCT FROM ARRAY['dincr_app']::name[]
--          OR cmd IS DISTINCT FROM 'ALL' OR qual IS DISTINCT FROM 'true' OR with_check IS DISTINCT FROM 'true')
-- UNION ALL SELECT 'unexpected policy ' || policyname || ' on mail_connection_takeovers' FROM pg_policies
--   WHERE schemaname = 'public' AND tablename = 'mail_connection_takeovers' AND policyname <> 'dincr_app_access';
