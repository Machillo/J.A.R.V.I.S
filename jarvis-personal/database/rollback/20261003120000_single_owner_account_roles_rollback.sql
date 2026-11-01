-- Rollback of 20261003120000_single_owner_account_roles.sql.
--
-- Restores the previous schema: accounts.role accepts ('user','admin','owner') again,
-- allowed_users.role loses its CHECK, and workspace_members.member_role comes back with its
-- old CHECK; every existing membership is the workspace owner's own (the migration verified
-- it), so it is restored as 'owner', and the column default stays 'member' as before. The
-- P0.2d code still refuses any role other than user/owner at login and never reads
-- member_role, so rolling back only relaxes the database; code from before #318 (which reads
-- member_role at login) works again on the restored column. The legacy diagnostic view
-- v_account_workspace_migration_status is recreated as it was, without any grant to the API roles.
--
-- Run only under docs/security/migration-safety-protocol.md: BACKUP_VERIFIED gate, a second
-- reviewer, psql -v ON_ERROR_STOP=1 as the owner, one transaction.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

ALTER TABLE public.allowed_users DROP CONSTRAINT IF EXISTS allowed_users_role_check;

ALTER TABLE public.workspace_members
    ADD COLUMN IF NOT EXISTS member_role TEXT NOT NULL DEFAULT 'owner'
    CHECK (member_role IN ('owner', 'admin', 'member', 'viewer'));
ALTER TABLE public.workspace_members ALTER COLUMN member_role SET DEFAULT 'member';

CREATE VIEW public.v_account_workspace_migration_status AS
SELECT au.id AS legacy_allowed_user_id,
       au.email AS legacy_email,
       a.id AS account_id,
       a.supabase_user_id,
       a.role AS account_role,
       w.id AS personal_workspace_id,
       w.name AS personal_workspace_name,
       wm.member_role,
       (a.id IS NOT NULL AND w.id IS NOT NULL AND wm.id IS NOT NULL) AS foundation_ready
FROM public.allowed_users au
LEFT JOIN public.accounts a ON a.legacy_allowed_user_id = au.id
LEFT JOIN public.workspaces w ON w.owner_account_id = a.id AND w.workspace_type = 'personal'
    AND w.workspace_key = 'personal:' || a.id::text
LEFT JOIN public.workspace_members wm ON wm.workspace_id = w.id AND wm.account_id = a.id;
REVOKE ALL ON public.v_account_workspace_migration_status FROM PUBLIC;
DO $$
DECLARE api_role text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role', 'dincr_app'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format('REVOKE ALL ON public.v_account_workspace_migration_status FROM %I', api_role);
        END IF;
    END LOOP;
END $$;

ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS accounts_role_check;
ALTER TABLE public.accounts
    ADD CONSTRAINT accounts_role_check CHECK (role IN ('user', 'admin', 'owner'));

COMMIT;
