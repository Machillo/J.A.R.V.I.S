-- History a user chooses to import before connecting Gmail or Outlook.
--
-- The choice ("current_month" or "current_year") is stored on the server-side
-- OAuth flow when the connection starts and copied to the mailbox connection
-- when the same account/workspace completes it. The first sync of that mailbox
-- scans from import_since. NULL on existing connections means the window used
-- before this change: January 1st of the current year.
--
-- Apply BEFORE deploying the code that reads these columns (without them the
-- connect endpoints and the mail status return 500 for every VIP user).
-- Locks: ADD COLUMN without default and ADD CONSTRAINT take ACCESS EXCLUSIVE on
-- both tables until COMMIT (no table rewrite; the new columns are all NULL, so
-- VALIDATE is instant). lock_timeout makes it fail fast instead of queueing
-- behind a running mail sync; retry when that happens.
--
-- Rollback (after reverting the code):
--   ALTER TABLE public.finva_gmail_connections
--       DROP CONSTRAINT IF EXISTS finva_gmail_connections_import_scope_check,
--       DROP COLUMN IF EXISTS import_since,
--       DROP COLUMN IF EXISTS import_scope;
--   ALTER TABLE public.mail_oauth_flows
--       DROP CONSTRAINT IF EXISTS mail_oauth_flows_import_scope_check,
--       DROP COLUMN IF EXISTS import_scope;
BEGIN;

SET LOCAL lock_timeout = '5s';

ALTER TABLE public.mail_oauth_flows
    ADD COLUMN IF NOT EXISTS import_scope TEXT;

ALTER TABLE public.finva_gmail_connections
    ADD COLUMN IF NOT EXISTS import_scope TEXT,
    ADD COLUMN IF NOT EXISTS import_since DATE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'mail_oauth_flows_import_scope_check'
          AND conrelid = 'public.mail_oauth_flows'::regclass
    ) THEN
        ALTER TABLE public.mail_oauth_flows
            ADD CONSTRAINT mail_oauth_flows_import_scope_check
            CHECK (import_scope IS NULL OR import_scope IN ('current_month', 'current_year')) NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'finva_gmail_connections_import_scope_check'
          AND conrelid = 'public.finva_gmail_connections'::regclass
    ) THEN
        ALTER TABLE public.finva_gmail_connections
            ADD CONSTRAINT finva_gmail_connections_import_scope_check
            CHECK (import_scope IS NULL OR import_scope IN ('current_month', 'current_year')) NOT VALID;
    END IF;
END $$;

ALTER TABLE public.mail_oauth_flows VALIDATE CONSTRAINT mail_oauth_flows_import_scope_check;
ALTER TABLE public.finva_gmail_connections VALIDATE CONSTRAINT finva_gmail_connections_import_scope_check;

COMMIT;
