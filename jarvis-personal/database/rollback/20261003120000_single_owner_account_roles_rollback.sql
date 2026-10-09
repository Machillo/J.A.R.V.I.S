-- Rollback of 20261003120000_single_owner_account_roles.sql.
--
-- Restores the previous schema: accounts.role accepts ('user','admin','owner') again,
-- allowed_users.role loses its CHECK, and workspace_members.member_role comes back with its
-- old CHECK; every existing membership is the workspace owner's own (the migration verified
-- it), so it is restored as 'owner', and the column default stays 'member' as before. The
-- P0.2d code still refuses any role other than user/owner at login and never reads
-- member_role, so rolling back only relaxes the database; code from before #318 (which reads
-- member_role at login) works again on the restored column.
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

ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS accounts_role_check;
ALTER TABLE public.accounts
    ADD CONSTRAINT accounts_role_check CHECK (role IN ('user', 'admin', 'owner'));

COMMIT;
