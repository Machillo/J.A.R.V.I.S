-- One live connection per mailbox across every DINCR account and workspace,
-- identified by a stable provider identity, with an audited takeover of stale ones.
--
-- finva_gmail_connections holds Gmail and Outlook mailboxes. Until now it was
-- unique only per account and per workspace, so two accounts could connect the
-- same mailbox and import its messages into both. This migration adds:
-- - mailbox_email: the provider-scoped canonical address, '<provider>:<address>'
--   (lower, trimmed; for gmail.com and googlemail.com without dots and "+tag", as
--   gmail.com). A Gmail and a Microsoft mailbox never match each other, even when
--   a Microsoft account reports a gmail.com address. google_email stays for display;
-- - mailbox_key: the stable identity. New connections store 'google:<sub>' or
--   'microsoft:<tenant>:<id>' when the provider returns them; existing rows are
--   backfilled from their scoped canonical address only ('email:<mailbox_email>'),
--   never from a legacy user id;
-- - provider_subject / provider_tenant on connections and OAuth flows;
-- - a unique index on each of mailbox_key and mailbox_email among live rows
--   (status <> 'disabled'): a disconnected mailbox is free again;
-- - mail_connection_takeovers: audit of a verified takeover of a stale connection
--   (backend/user_product/mail_oauth.py claim_mailbox). Account ids only.
--
-- Aborts with SQLSTATE MB001, changing nothing, if two live connections already
-- share a canonical mailbox: a human decides which one stays (never deleted here).
-- One transaction: apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED
-- gate) as the table owner (postgres), BEFORE the code of this PR is deployed
-- (the code writes the new columns). The table is small; the lock lasts milliseconds.
-- Rows written by the previous code between this migration and the deploy have a
-- NULL mailbox_email: the application still compares them by display address and
-- provider scope. RE-RUN this migration right after the deploy (a listed step; it
-- is idempotent) so those rows get their identity.
--
-- Preflight (read-only, prints no address): must return 0.
--   SELECT count(*) FROM (SELECT 1 FROM public.finva_gmail_connections WHERE status <> 'disabled'
--    GROUP BY 'Mail.Read' = ANY(granted_scopes),
--             CASE WHEN split_part(lower(btrim(google_email)), '@', 2) IN ('gmail.com', 'googlemail.com')
--                  THEN replace(split_part(split_part(lower(btrim(google_email)), '@', 1), '+', 1), '.', '') || '@gmail.com'
--                  ELSE lower(btrim(google_email)) END
--    HAVING count(*) > 1) duplicated_mailboxes;
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926110000_mailbox_single_owner_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

-- No connection is written between the backfill, the duplicate check and the index build.
LOCK TABLE public.finva_gmail_connections IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE public.finva_gmail_connections
    ADD COLUMN IF NOT EXISTS mailbox_email TEXT,
    ADD COLUMN IF NOT EXISTS mailbox_key TEXT,
    ADD COLUMN IF NOT EXISTS provider_subject TEXT,
    ADD COLUMN IF NOT EXISTS provider_tenant TEXT;
ALTER TABLE public.mail_oauth_flows
    ADD COLUMN IF NOT EXISTS provider_subject TEXT,
    ADD COLUMN IF NOT EXISTS provider_tenant TEXT;

-- Backfill from the canonical address only (same rule as mail_oauth.mailbox_email):
-- the provider comes from the stored scope, as everywhere else in the application.
UPDATE public.finva_gmail_connections SET mailbox_email =
    CASE WHEN 'Mail.Read' = ANY(granted_scopes) THEN 'microsoft:' ELSE 'gmail:' END ||
    CASE WHEN split_part(lower(btrim(google_email)), '@', 2) IN ('gmail.com', 'googlemail.com')
         THEN replace(split_part(split_part(lower(btrim(google_email)), '@', 1), '+', 1), '.', '') || '@gmail.com'
         ELSE lower(btrim(google_email)) END
WHERE mailbox_email IS NULL;
UPDATE public.finva_gmail_connections SET mailbox_key = 'email:' || mailbox_email WHERE mailbox_key IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.finva_gmail_connections
        WHERE status <> 'disabled'
        GROUP BY mailbox_email
        HAVING count(*) > 1
    ) OR EXISTS (
        SELECT 1 FROM public.finva_gmail_connections
        WHERE status <> 'disabled'
        GROUP BY mailbox_key
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'a mailbox is live in more than one connection; resolve it before this migration'
            USING ERRCODE = 'MB001';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_finva_mail_connections_live_mailbox
    ON public.finva_gmail_connections (mailbox_email)
    WHERE status <> 'disabled';
CREATE UNIQUE INDEX IF NOT EXISTS uq_finva_mail_connections_live_identity
    ON public.finva_gmail_connections (mailbox_key)
    WHERE status <> 'disabled';

-- Superseded: the older per-account index also counted disconnected rows, so a
-- mailbox disconnected in one workspace could never be connected in another
-- workspace of the same account. (workspace_id, google_email) stays unique:
-- reconnecting in the same workspace reuses its row.
DROP INDEX IF EXISTS public.finva_gmail_connections_account_email_key;

CREATE TABLE IF NOT EXISTS public.mail_connection_takeovers (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider IN ('gmail', 'microsoft')),
    previous_connection_id BIGINT REFERENCES public.finva_gmail_connections(id) ON DELETE SET NULL,
    previous_account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
    new_account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
    reason TEXT NOT NULL CHECK (reason IN ('access_lost', 'plan_inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.mail_connection_takeovers ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.mail_connection_takeovers FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON SEQUENCE public.mail_connection_takeovers_id_seq FROM anon, authenticated;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'missing index ' || n FROM unnest(ARRAY['uq_finva_mail_connections_live_mailbox','uq_finva_mail_connections_live_identity']) n
--  WHERE NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
--    WHERE c.relname = n AND i.indisunique AND i.indisvalid AND i.indrelid = 'public.finva_gmail_connections'::regclass)
-- UNION ALL
-- SELECT 'connection without identity' FROM public.finva_gmail_connections
--  WHERE mailbox_email IS NULL OR mailbox_key IS NULL HAVING count(*) > 0
-- UNION ALL
-- SELECT 'missing table mail_connection_takeovers' WHERE to_regclass('public.mail_connection_takeovers') IS NULL;
