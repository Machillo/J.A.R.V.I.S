-- One live connection per mailbox across every DINCR account and workspace.
--
-- finva_gmail_connections holds Gmail and Outlook mailboxes. Until now it was
-- unique only per account and per workspace, so two accounts could connect the
-- same mailbox and import its messages into both. The mailbox identity is
-- lower(btrim(google_email)); a connection is live until it is disconnected
-- (status 'disabled', its token deleted). A disconnected mailbox is free again.
-- The application checks the same rule first (backend/user_product/mail_oauth.py
-- ensure_mailbox_available) and answers a generic 409; this index closes the
-- race between two concurrent completions.
--
-- Aborts with SQLSTATE MB001, changing nothing, if two live connections already
-- share a mailbox: a human decides which one stays (never deleted here).
-- One transaction: apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED
-- gate) as the table owner (postgres). CREATE UNIQUE INDEX (not CONCURRENTLY,
-- which cannot run in a transaction) blocks writes to finva_gmail_connections
-- while it builds; the table is small, so this takes milliseconds.
--
-- Preflight (read-only, prints no address): must return 0.
--   SELECT count(*) FROM (SELECT 1 FROM public.finva_gmail_connections WHERE status <> 'disabled'
--    GROUP BY lower(btrim(google_email)) HAVING count(*) > 1) duplicated_mailboxes;
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback (one transaction, BACKUP_VERIFIED, second reviewer):
--   CREATE UNIQUE INDEX IF NOT EXISTS finva_gmail_connections_account_email_key
--     ON public.finva_gmail_connections(account_id, lower(google_email));
--   DROP INDEX IF EXISTS public.uq_finva_mail_connections_live_mailbox;
--   (recreating the old index fails if an account now has the same mailbox in two
--   workspaces, one of them disconnected; the application check keeps working
--   without either index, minus the race protection).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

-- No connection is written between the duplicate check and the index build.
LOCK TABLE public.finva_gmail_connections IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.finva_gmail_connections
        WHERE status <> 'disabled'
        GROUP BY lower(btrim(google_email))
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'a mailbox is live in more than one connection; resolve it before this migration'
            USING ERRCODE = 'MB001';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_finva_mail_connections_live_mailbox
    ON public.finva_gmail_connections (lower(btrim(google_email)))
    WHERE status <> 'disabled';

-- Superseded: the older per-account index also counted disconnected rows, so a
-- mailbox disconnected in one workspace could never be connected in another
-- workspace of the same account. The live-mailbox index above covers every
-- account and workspace. (workspace_id, google_email) stays unique: reconnecting
-- in the same workspace reuses its row.
DROP INDEX IF EXISTS public.finva_gmail_connections_account_email_key;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'missing index' WHERE NOT EXISTS (
--   SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
--    WHERE c.relname = 'uq_finva_mail_connections_live_mailbox' AND i.indisunique AND i.indisvalid
--      AND i.indrelid = 'public.finva_gmail_connections'::regclass)
-- UNION ALL
-- SELECT 'mailbox live twice' FROM public.finva_gmail_connections WHERE status <> 'disabled'
--  GROUP BY lower(btrim(google_email)) HAVING count(*) > 1;
