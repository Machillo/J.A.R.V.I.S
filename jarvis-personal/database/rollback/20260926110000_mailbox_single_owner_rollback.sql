-- Rollback of 20260926110000_mailbox_single_owner.sql. Run it AFTER reverting the
-- code (the new code writes these columns), under BACKUP_VERIFIED with a second
-- reviewer. It drops the takeover audit (export it first if it must be kept) and
-- the identity columns; no connection, message or transaction is touched.
-- Recreating the old per-account index fails (and the whole rollback aborts) if
-- an account now has the same address in two workspaces, one of them disconnected:
-- decide that case by hand first.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

CREATE UNIQUE INDEX IF NOT EXISTS finva_gmail_connections_account_email_key
    ON public.finva_gmail_connections(account_id, lower(google_email));
DROP INDEX IF EXISTS public.uq_finva_mail_connections_live_identity;
DROP INDEX IF EXISTS public.uq_finva_mail_connections_live_mailbox;
DROP TABLE IF EXISTS public.mail_connection_takeovers;
ALTER TABLE public.finva_gmail_connections
    DROP COLUMN IF EXISTS mailbox_email,
    DROP COLUMN IF EXISTS mailbox_key,
    DROP COLUMN IF EXISTS provider_subject,
    DROP COLUMN IF EXISTS provider_tenant;
ALTER TABLE public.mail_oauth_flows
    DROP COLUMN IF EXISTS provider_subject,
    DROP COLUMN IF EXISTS provider_tenant;

COMMIT;
