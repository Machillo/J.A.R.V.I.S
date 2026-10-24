-- Single Owner authority (master plan P0.2d, phase 3). DINCR authority is 'user'
-- (Free/Basic/VIP; the plan decides the tier) or 'owner' (the single verified Owner). There is
-- no 'admin', 'viewer' or 'member' role (decision 2026-10-03).
--
-- - accounts.role: CHECK narrowed from ('user','admin','owner') to ('user','owner').
-- - allowed_users.role: CHECK added ('user','owner'); it had none (any text was accepted).
-- - workspace_members.member_role: column dropped. workspace_members stays (account ->
--   personal workspace, status 'active'): technical isolation used by login, 3 RLS policies
--   and 3 integrity functions, none of which reads member_role. Workspace data owner is never
--   the DINCR Owner. Shared financial workspaces are a future beta candidate, out of scope.
--
-- Nothing is rewritten, promoted or silently transformed: the migration aborts before any
-- change if an account or allowlist row holds a role other than user/owner, if a membership
-- holds a member_role other than 'owner' or 'member', or if any membership is not the
-- workspace owner's own (a shared membership must be reviewed by a human). 'member' is
-- expected only as the column default on memberships created after the P0.2d code PR
-- stopped writing the column. Production on 2026-10-03 (aggregate, read-only): accounts
-- owner=1, user=8; allowed_users owner=1, user=8; workspace_members owner=9, all the
-- workspace owner's own.
--
-- DEPLOY ORDER (CRITICAL): apply only after the P0.2d code PR (#318) is deployed and verified.
-- Earlier code reads workspace_members.member_role at login; dropping it first would break
-- every login. The deployed #318 code never reads, writes or depends on member_role.
-- One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate),
-- as the role that owns the tables (postgres). ALTER TABLE takes an ACCESS EXCLUSIVE lock on
-- each table until COMMIT; all are tiny (one row per account), so it lasts milliseconds, but
-- logins wait on it: apply at low traffic.
--
-- Preflight (read-only): must return zero rows.
--   SELECT 'accounts.role=' || role, count(*) FROM public.accounts WHERE role NOT IN ('user', 'owner') GROUP BY role
--   UNION ALL
--   SELECT 'allowed_users.role=' || role, count(*) FROM public.allowed_users WHERE role NOT IN ('user', 'owner') GROUP BY role
--   UNION ALL
--   SELECT 'workspace_members.member_role=' || member_role, count(*) FROM public.workspace_members
--    WHERE member_role NOT IN ('owner', 'member') GROUP BY member_role
--   UNION ALL
--   SELECT 'membership of another account', count(*) FROM public.workspace_members wm
--    JOIN public.workspaces w ON w.id = wm.workspace_id WHERE wm.account_id <> w.owner_account_id HAVING count(*) > 0;
-- No grant changes: dincr_app keeps exactly its privileges (CHECKs need none).
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20261003120000_single_owner_account_roles_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $$
DECLARE
    invalid_accounts integer;
    invalid_allowed integer;
    unexpected_member_roles integer := 0;
    shared_memberships integer;
BEGIN
    SELECT count(*) INTO invalid_accounts FROM public.accounts WHERE role NOT IN ('user', 'owner');
    SELECT count(*) INTO invalid_allowed FROM public.allowed_users WHERE role NOT IN ('user', 'owner');
    IF invalid_accounts > 0 OR invalid_allowed > 0 THEN
        RAISE EXCEPTION 'P0.2d: % account(s) and % allowlist row(s) hold a role other than user/owner; review them, never convert or promote',
            invalid_accounts, invalid_allowed;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND table_name = 'workspace_members' AND column_name = 'member_role') THEN
        EXECUTE $q$SELECT count(*) FROM public.workspace_members WHERE member_role NOT IN ('owner', 'member')$q$
            INTO unexpected_member_roles;
    END IF;
    SELECT count(*) INTO shared_memberships
    FROM public.workspace_members wm JOIN public.workspaces w ON w.id = wm.workspace_id
    WHERE wm.account_id <> w.owner_account_id;
    IF unexpected_member_roles > 0 OR shared_memberships > 0 THEN
        RAISE EXCEPTION 'P0.2d: % membership(s) with an unexpected member_role and % membership(s) of another account; review them, never convert or drop silently',
            unexpected_member_roles, shared_memberships;
    END IF;
END $$;

ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS accounts_role_check;
ALTER TABLE public.accounts
    ADD CONSTRAINT accounts_role_check CHECK (role IN ('user', 'owner'));

ALTER TABLE public.allowed_users DROP CONSTRAINT IF EXISTS allowed_users_role_check;
ALTER TABLE public.allowed_users
    ADD CONSTRAINT allowed_users_role_check CHECK (role IN ('user', 'owner'));

-- Membership has no role (its CHECK goes with the column).
ALTER TABLE public.workspace_members DROP COLUMN IF EXISTS member_role;

COMMIT;

-- Postflight (read-only): must return zero rows.
--   SELECT conrelid::regclass, conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conname IN ('accounts_role_check', 'allowed_users_role_check')
--      AND pg_get_constraintdef(oid) LIKE '%admin%'
--   UNION ALL
--   SELECT 'missing', name, NULL FROM unnest(ARRAY['accounts_role_check', 'allowed_users_role_check']) name
--    WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = name)
--   UNION ALL
--   SELECT 'workspace_members.member_role still exists', column_name, NULL FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'workspace_members' AND column_name = 'member_role';
