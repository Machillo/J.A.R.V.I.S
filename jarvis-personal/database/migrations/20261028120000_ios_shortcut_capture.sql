-- iOS Shortcuts capture: Apple Pay purchases and bank SMS become review candidates.
--
-- The Shortcuts automations (Transacción, Mensaje) run App Intents in the background, without
-- the app's session. They authenticate with a limited token whose only permission is to create
-- review candidates for the account and workspace it was issued to:
--   - shortcut_tokens keeps only the SHA-256 of the token (never the token), one active token per
--     account, revocable (revoked_at). Rows go with the account and its workspace (ON DELETE
--     CASCADE), so account deletion leaves nothing behind. RLS is enabled and only the backend
--     reads or writes it: the application role dincr_app gets SELECT/INSERT/UPDATE and one
--     dincr_app_access policy; anon/authenticated get nothing.
--   - finva_email_candidates.email_message_id drops NOT NULL: a candidate captured by Shortcuts
--     has no email behind it (source_type 'api'). Existing rows all have one and keep it; mail
--     code always sets it. Catalog-only, no table rewrite.
--   - uq_finva_candidates_capture_key: one candidate per (account, workspace, capture key) for
--     candidates captured by Shortcuts (source_record_key '<provider>:<Idempotency-Key>'), so a
--     retried request never creates a second candidate. Mail rows (source_type email/statement)
--     are outside the partial index.
--
-- Idempotent (a second run changes nothing). One transaction: apply it with
-- backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
-- Must be applied BEFORE the code that writes these rows deploys (PRE-MERGE GATE).
--
-- Preflight (read-only): must return zero rows.
--   SELECT 'missing table ' || t AS problem FROM unnest(ARRAY['finva_email_candidates','accounts','workspaces']) t
--   WHERE to_regclass('public.' || t) IS NULL
--   UNION ALL
--   SELECT 'api candidates already present: ' || count(*) FROM public.finva_email_candidates
--   WHERE source_type = 'api' HAVING count(*) > 0;
-- Postflight (read-only, after COMMIT): must return zero rows.
--   SELECT 'shortcut_tokens missing or without RLS' AS problem
--   WHERE NOT EXISTS (SELECT 1 FROM pg_class WHERE oid = to_regclass('public.shortcut_tokens') AND relrowsecurity)
--   UNION ALL
--   SELECT 'email_message_id still NOT NULL' FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'finva_email_candidates' AND column_name = 'email_message_id'
--     AND is_nullable = 'NO'
--   UNION ALL
--   SELECT 'capture key index missing' WHERE to_regclass('public.uq_finva_candidates_capture_key') IS NULL
--   UNION ALL
--   SELECT 'grant to ' || grantee FROM information_schema.role_table_grants
--   WHERE table_schema = 'public' AND table_name = 'shortcut_tokens' AND grantee IN ('anon', 'authenticated');

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RAISE EXCEPTION 'role dincr_app is missing: apply 20260926150000 first' USING ERRCODE = 'SC001';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.shortcut_tokens (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_shortcut_tokens_hash ON public.shortcut_tokens (token_hash);
-- One active token per account: issuing a new one revokes the previous one first.
CREATE UNIQUE INDEX IF NOT EXISTS uq_shortcut_tokens_active_account ON public.shortcut_tokens (account_id) WHERE revoked_at IS NULL;

ALTER TABLE public.shortcut_tokens ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.shortcut_tokens FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.shortcut_tokens_id_seq FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.shortcut_tokens TO dincr_app;
GRANT USAGE ON SEQUENCE public.shortcut_tokens_id_seq TO dincr_app;
-- Re-created on every run, so a re-run leaves exactly this policy.
DROP POLICY IF EXISTS dincr_app_access ON public.shortcut_tokens;
CREATE POLICY dincr_app_access ON public.shortcut_tokens AS PERMISSIVE FOR ALL TO dincr_app
    USING (true) WITH CHECK (true);

ALTER TABLE public.finva_email_candidates ALTER COLUMN email_message_id DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_finva_candidates_capture_key
    ON public.finva_email_candidates (account_id, workspace_id, source_record_key)
    WHERE source_type = 'api' AND source_record_key IS NOT NULL;

COMMIT;
