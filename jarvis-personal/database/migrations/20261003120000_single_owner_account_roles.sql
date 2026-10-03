-- Single Owner authority (master plan P0.2d, phase 3): the stored account roles are only
-- 'user' (Free/Basic/VIP; the plan decides the tier) and 'owner' (the single verified Owner).
-- DINCR has no 'admin' (nor 'viewer'): the backend no longer creates, serves or promotes them
-- (P0.2d code PR); this makes the database refuse them too.
--
-- - accounts.role: CHECK narrowed from ('user','admin','owner') to ('user','owner').
-- - allowed_users.role: CHECK added ('user','owner'); it had none (any text was accepted).
--
-- No row is rewritten, deleted or promoted. If any row holds another role, the migration
-- aborts before any change (a stored admin is invalid: it must be reviewed by a human,
-- never converted). Production on 2026-10-03 (aggregate, read-only): accounts owner=1,
-- user=8; allowed_users owner=1, user=8; no other value.
-- workspace_members.member_role (a different, unused membership concept) is not touched.
--
-- The code runs before and after this migration (it never writes another role).
-- One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate),
-- as the role that owns both tables (postgres). ALTER TABLE takes an ACCESS EXCLUSIVE lock on
-- each table until COMMIT; both are tiny (one row per account), so the validation is
-- milliseconds, but logins wait on it: apply at low traffic.
--
-- Preflight (read-only): must return zero rows.
--   SELECT 'accounts.role=' || role, count(*) FROM public.accounts WHERE role NOT IN ('user', 'owner') GROUP BY role
--   UNION ALL
--   SELECT 'allowed_users.role=' || role, count(*) FROM public.allowed_users WHERE role NOT IN ('user', 'owner') GROUP BY role;
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
BEGIN
    SELECT count(*) INTO invalid_accounts FROM public.accounts WHERE role NOT IN ('user', 'owner');
    SELECT count(*) INTO invalid_allowed FROM public.allowed_users WHERE role NOT IN ('user', 'owner');
    IF invalid_accounts > 0 OR invalid_allowed > 0 THEN
        RAISE EXCEPTION 'P0.2d: % account(s) and % allowlist row(s) hold a role other than user/owner; review them, never convert or promote',
            invalid_accounts, invalid_allowed;
    END IF;
END $$;

ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS accounts_role_check;
ALTER TABLE public.accounts
    ADD CONSTRAINT accounts_role_check CHECK (role IN ('user', 'owner'));

ALTER TABLE public.allowed_users DROP CONSTRAINT IF EXISTS allowed_users_role_check;
ALTER TABLE public.allowed_users
    ADD CONSTRAINT allowed_users_role_check CHECK (role IN ('user', 'owner'));

COMMIT;

-- Postflight (read-only): must return zero rows.
--   SELECT conrelid::regclass, conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conname IN ('accounts_role_check', 'allowed_users_role_check')
--      AND pg_get_constraintdef(oid) LIKE '%admin%'
--   UNION ALL
--   SELECT 'missing', name, NULL FROM unnest(ARRAY['accounts_role_check', 'allowed_users_role_check']) name
--    WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = name);
