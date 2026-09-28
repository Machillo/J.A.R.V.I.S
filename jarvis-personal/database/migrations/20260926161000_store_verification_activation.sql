-- Verified App Store / Google Play purchases: ACTIVATION phase (runtime access only).
--
-- Gives the application role (dincr_app, 20260926150000) exactly what the store
-- verification code (backend/product_ops/store_state.py, store_verification.py) runs
-- on the tables that 20260926160000 created, and nothing else:
-- - store_customer_tokens:    SELECT, INSERT
-- - store_purchases:          SELECT, INSERT, UPDATE (ON CONFLICT DO UPDATE, status updates)
-- - store_purchase_conflicts: SELECT, INSERT, and USAGE on its id sequence
-- - store_revocations:        SELECT, INSERT, UPDATE (ON CONFLICT DO UPDATE, reversals)
-- - one dincr_app_access policy per table (RLS is on; without a policy the role reads
--   no rows). No DELETE: account deletion cascades as the table owner.
-- No table or column is created here (that is 160000's), and anon/authenticated get nothing.
--
-- This does NOT turn store verification on. The code stays off (503, no access to these
-- tables) until a human sets DINCR_STORE_VERIFICATION_ENABLED=1, after the postflights
-- of 160000 and of this file both return zero rows (docs/billing/store-verification.md).
--
-- PRE-APPLY GATE: 20260926160000 applied and its postflight clean; dincr_app exists.
-- Aborts otherwise (SV004 / SV002) and changes nothing.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres.
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926161000_store_verification_activation_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RAISE EXCEPTION 'role dincr_app is missing: apply 20260926150000 first' USING ERRCODE = 'SV002';
    END IF;
    IF to_regclass('public.store_customer_tokens') IS NULL OR to_regclass('public.store_purchases') IS NULL
       OR to_regclass('public.store_purchase_conflicts') IS NULL OR to_regclass('public.store_revocations') IS NULL
       OR to_regclass('public.store_purchase_conflicts_id_seq') IS NULL THEN
        RAISE EXCEPTION 'store verification schema is missing: apply 20260926160000 first' USING ERRCODE = 'SV004';
    END IF;
END $$;

GRANT SELECT, INSERT ON TABLE public.store_customer_tokens TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.store_purchases TO dincr_app;
GRANT SELECT, INSERT ON TABLE public.store_purchase_conflicts TO dincr_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.store_revocations TO dincr_app;
GRANT USAGE ON SEQUENCE public.store_purchase_conflicts_id_seq TO dincr_app;

-- Re-created on every run, so a re-run leaves exactly this policy.
DROP POLICY IF EXISTS dincr_app_access ON public.store_customer_tokens;
CREATE POLICY dincr_app_access ON public.store_customer_tokens AS PERMISSIVE FOR ALL TO dincr_app
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS dincr_app_access ON public.store_purchases;
CREATE POLICY dincr_app_access ON public.store_purchases AS PERMISSIVE FOR ALL TO dincr_app
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS dincr_app_access ON public.store_purchase_conflicts;
CREATE POLICY dincr_app_access ON public.store_purchase_conflicts AS PERMISSIVE FOR ALL TO dincr_app
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS dincr_app_access ON public.store_revocations;
CREATE POLICY dincr_app_access ON public.store_revocations AS PERMISSIVE FOR ALL TO dincr_app
    USING (true) WITH CHECK (true);

COMMIT;

-- Postflight (read-only): must return zero rows.
-- WITH expected(t, p) AS (VALUES
--     ('store_customer_tokens', 'SELECT'), ('store_customer_tokens', 'INSERT'),
--     ('store_purchases', 'SELECT'), ('store_purchases', 'INSERT'), ('store_purchases', 'UPDATE'),
--     ('store_purchase_conflicts', 'SELECT'), ('store_purchase_conflicts', 'INSERT'),
--     ('store_revocations', 'SELECT'), ('store_revocations', 'INSERT'), ('store_revocations', 'UPDATE')),
-- actual(r, t, p) AS (
--     SELECT r, t, p
--     FROM unnest(ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations']) t,
--          unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r,
--          unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER']) p
--     WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) AND has_table_privilege(r, 'public.' || t, p))
-- SELECT 'dincr_app lacks ' || p || ' on ' || t FROM expected
--   WHERE ('dincr_app', t, p) NOT IN (SELECT r, t, p FROM actual)
-- UNION ALL SELECT r || ' has extra ' || p || ' on ' || t FROM actual
--   WHERE NOT (r = 'dincr_app' AND (t, p) IN (SELECT t, p FROM expected))
-- UNION ALL SELECT 'dincr_app lacks USAGE on store_purchase_conflicts_id_seq'
--   WHERE NOT has_sequence_privilege('dincr_app', 'public.store_purchase_conflicts_id_seq', 'USAGE')
-- UNION ALL SELECT r || ' has ' || p || ' on store_purchase_conflicts_id_seq'
--   FROM unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r, unnest(ARRAY['SELECT', 'UPDATE']) p
--   WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
--     AND has_sequence_privilege(r, 'public.store_purchase_conflicts_id_seq', p)
-- UNION ALL SELECT r || ' has USAGE on store_purchase_conflicts_id_seq'
--   FROM unnest(ARRAY['anon', 'authenticated']) r
--   WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
--     AND has_sequence_privilege(r, 'public.store_purchase_conflicts_id_seq', 'USAGE')
-- UNION ALL SELECT 'row level security off on ' || relname FROM pg_class
--   WHERE relname IN ('store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations')
--     AND NOT relrowsecurity
-- UNION ALL SELECT 'missing policy dincr_app_access on ' || t
--   FROM unnest(ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations']) t
--   WHERE NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = t
--                     AND policyname = 'dincr_app_access')
-- UNION ALL SELECT 'wrong policy dincr_app_access on ' || tablename || ': ' || concat_ws(', ',
--          CASE WHEN permissive IS DISTINCT FROM 'PERMISSIVE' THEN 'not permissive' END,
--          CASE WHEN roles IS DISTINCT FROM ARRAY['dincr_app']::name[] THEN 'roles ' || roles::text END,
--          CASE WHEN cmd IS DISTINCT FROM 'ALL' THEN 'command ' || cmd END,
--          CASE WHEN qual IS DISTINCT FROM 'true' THEN 'USING ' || coalesce(qual, 'none') END,
--          CASE WHEN with_check IS DISTINCT FROM 'true' THEN 'WITH CHECK ' || coalesce(with_check, 'none') END)
--   FROM pg_policies
--   WHERE schemaname = 'public' AND policyname = 'dincr_app_access'
--     AND tablename IN ('store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations')
--     AND (permissive IS DISTINCT FROM 'PERMISSIVE' OR roles IS DISTINCT FROM ARRAY['dincr_app']::name[]
--          OR cmd IS DISTINCT FROM 'ALL' OR qual IS DISTINCT FROM 'true' OR with_check IS DISTINCT FROM 'true')
-- UNION ALL SELECT 'unexpected policy ' || policyname || ' on ' || tablename FROM pg_policies
--   WHERE schemaname = 'public'
--     AND tablename IN ('store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations')
--     AND policyname <> 'dincr_app_access';
