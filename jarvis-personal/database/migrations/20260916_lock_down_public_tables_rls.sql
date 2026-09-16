-- FINVA security hardening: the browser only uses Supabase Auth. Application
-- data is served by the authenticated FastAPI backend, so public Data API
-- roles must not have direct access to any application table.
--
-- This migration intentionally creates no permissive policies. With RLS
-- enabled and no policies, Postgres denies every row to anon/authenticated.
-- The database owner used by the backend continues to operate normally.

BEGIN;

DO $rls_lockdown$
DECLARE
    table_record RECORD;
BEGIN
    FOR table_record IN
        SELECT namespace.nspname AS schema_name, relation.relname AS table_name
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relkind IN ('r', 'p')
          AND NOT relation.relrowsecurity
          -- Do not modify tables owned by installed extensions such as PostGIS.
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend AS dependency
              WHERE dependency.classid = 'pg_class'::regclass
                AND dependency.objid = relation.oid
                AND dependency.deptype = 'e'
          )
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
            table_record.schema_name,
            table_record.table_name
        );
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON TABLE %I.%I FROM anon, authenticated',
            table_record.schema_name,
            table_record.table_name
        );
    END LOOP;
END
$rls_lockdown$;

-- Tables created later by the same migration/runtime database owner start
-- without Data API privileges. Each new migration must still enable RLS.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated;

-- Serial/identity sequences are backend-only as well.
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated;

-- Abort the transaction if any application table was left without RLS.
DO $verify_rls$
DECLARE
    unprotected_tables TEXT;
BEGIN
    SELECT string_agg(format('%I.%I', namespace.nspname, relation.relname), ', ' ORDER BY relation.relname)
      INTO unprotected_tables
      FROM pg_class AS relation
      JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname = 'public'
       AND relation.relkind IN ('r', 'p')
       AND NOT relation.relrowsecurity
       AND NOT EXISTS (
           SELECT 1
           FROM pg_depend AS dependency
           WHERE dependency.classid = 'pg_class'::regclass
             AND dependency.objid = relation.oid
             AND dependency.deptype = 'e'
       );

    IF unprotected_tables IS NOT NULL THEN
        RAISE EXCEPTION 'Public application tables still missing RLS: %', unprotected_tables;
    END IF;
END
$verify_rls$;

COMMIT;
