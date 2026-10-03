-- Rollback of 20261003120000_single_owner_account_roles.sql.
--
-- Restores the previous constraints: accounts.role accepts ('user','admin','owner') again and
-- allowed_users.role loses its CHECK. No row changes. The P0.2d code still refuses any
-- role other than user/owner at login and never creates one, so rolling back only relaxes
-- the database; it does not bring back an admin identity.
--
-- Run only under docs/security/migration-safety-protocol.md: BACKUP_VERIFIED gate, a second
-- reviewer, psql -v ON_ERROR_STOP=1 as the owner, one transaction.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

ALTER TABLE public.allowed_users DROP CONSTRAINT IF EXISTS allowed_users_role_check;

ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS accounts_role_check;
ALTER TABLE public.accounts
    ADD CONSTRAINT accounts_role_check CHECK (role IN ('user', 'admin', 'owner'));

COMMIT;
