-- Rollback of 20260928100000_mailbox_takeovers_app_access.sql.
--
-- Takes back from dincr_app only what 20260928100000 gave: its privileges on
-- mail_connection_takeovers, USAGE on its id sequence, and the dincr_app_access policy.
-- No table, column or row is touched: the schema and audit rows of 20260926110000 stay,
-- so this loses nothing and can be re-applied by applying 20260928100000 again.
--
-- PRE-ROLLBACK GATE: the code that claims mailboxes (PR #249) is reverted first. With
-- it deployed, a takeover would fail with "permission denied".
-- To roll back 20260926110000 as well, run this file first, then its own rollback.
-- BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RETURN;
    END IF;
    IF to_regclass('public.mail_connection_takeovers') IS NOT NULL THEN
        DROP POLICY IF EXISTS dincr_app_access ON public.mail_connection_takeovers;
        REVOKE ALL PRIVILEGES ON TABLE public.mail_connection_takeovers FROM dincr_app;
    END IF;
    IF to_regclass('public.mail_connection_takeovers_id_seq') IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON SEQUENCE public.mail_connection_takeovers_id_seq FROM dincr_app;
    END IF;
END $$;

COMMIT;
