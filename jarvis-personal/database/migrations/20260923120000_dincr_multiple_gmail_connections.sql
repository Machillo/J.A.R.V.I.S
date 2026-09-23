-- A DINCR workspace may authorize several Gmail inboxes. Keep the connection
-- id stable so existing messages, candidate reviews and scans remain intact.
BEGIN;

ALTER TABLE public.finva_gmail_connections
    DROP CONSTRAINT IF EXISTS finva_gmail_connections_account_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS finva_gmail_connections_account_email_key
    ON public.finva_gmail_connections(account_id, lower(google_email));

CREATE INDEX IF NOT EXISTS finva_gmail_connections_workspace_status_idx
    ON public.finva_gmail_connections(account_id, workspace_id, status);

COMMIT;
