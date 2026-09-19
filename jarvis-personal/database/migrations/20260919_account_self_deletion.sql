-- Allow a user's account deletion to remove every owned workspace and its data.
-- Run once in Supabase SQL Editor before enabling DELETE /auth/me.
BEGIN;

DO $$
DECLARE
    fk RECORD;
BEGIN
    -- Every single-column FK that points to a workspace becomes ownership
    -- cascading. This includes legacy financial tables added over time.
    FOR fk IN
        SELECT ns.nspname AS schema_name,
               child.relname AS table_name,
               c.conname,
               att.attname AS column_name
          FROM pg_constraint c
          JOIN pg_class child ON child.oid = c.conrelid
          JOIN pg_namespace ns ON ns.oid = child.relnamespace
          JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
         WHERE c.contype = 'f'
           AND c.confrelid = 'public.workspaces'::regclass
           AND cardinality(c.conkey) = 1
           AND ns.nspname = 'public'
           AND c.confdeltype <> 'c'
    LOOP
        EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT %I', fk.schema_name, fk.table_name, fk.conname);
        EXECUTE format(
            'ALTER TABLE %I.%I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES public.workspaces(id) ON DELETE CASCADE NOT VALID',
            fk.schema_name, fk.table_name, fk.conname, fk.column_name
        );
    END LOOP;
END $$;

ALTER TABLE public.workspaces
    DROP CONSTRAINT IF EXISTS workspaces_owner_account_id_fkey;
ALTER TABLE public.workspaces
    ADD CONSTRAINT workspaces_owner_account_id_fkey
    FOREIGN KEY (owner_account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

COMMIT;
