-- Mail secret boundary: the only way the application reaches Supabase Vault.
--
-- Mail refresh tokens (Gmail, Outlook) are Vault secrets. The application used to
-- read vault.decrypted_secrets and delete from vault.secrets directly, which needs
-- general Vault access. These SECURITY DEFINER functions (owner: postgres; safe
-- search_path; EXECUTE revoked from PUBLIC, anon and authenticated) handle only
-- DINCR mail tokens, and only for the account named in the token's description
-- ('DINCR <provider> refresh token for account <id>', 'FINVA' before the rename).
-- The dedicated application role gets EXECUTE in 20260926150000.
--
-- Aborts (APP02), changing nothing, if a live connection or pending flow references
-- a token whose description does not name its account: the ownership check would
-- lock that mailbox out, so a human decides first.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres,
-- BEFORE the code of this PR is deployed (the code calls these functions).
--
-- Preflight (read-only; must return 0):
--   SELECT count(*) FROM (SELECT c.refresh_token_secret_id AS secret_id, c.account_id FROM public.finva_gmail_connections c
--     UNION ALL SELECT f.pending_secret_id, f.account_id FROM public.mail_oauth_flows f) r
--   JOIN vault.secrets s ON s.id = r.secret_id
--   WHERE s.description !~ ('^(DINCR|FINVA) (Gmail|Microsoft) refresh token for account ' || r.account_id::TEXT || '$');
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926149000_mail_secret_boundary_rollback.sql
-- (only after reverting the code that calls these functions).

BEGIN;

SET LOCAL lock_timeout = '5s';

CREATE SCHEMA IF NOT EXISTS dincr_private;
REVOKE ALL ON SCHEMA dincr_private FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON SCHEMA dincr_private FROM anon, authenticated;
    END IF;
END $$;

-- The description every mail token has carried ('FINVA' before the rename).
CREATE OR REPLACE FUNCTION dincr_private.mail_secret_owned(p_description TEXT, p_account_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT p_description ~ ('^(DINCR|FINVA) (Gmail|Microsoft) refresh token for account ' || p_account_id::TEXT || '$')
$fn$;

CREATE OR REPLACE FUNCTION dincr_private.mail_secret_create(p_secret TEXT, p_account_id UUID, p_provider TEXT)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF p_provider NOT IN ('Gmail', 'Microsoft') OR p_account_id IS NULL
       OR NOT EXISTS (SELECT 1 FROM public.accounts WHERE id = p_account_id) THEN
        RAISE EXCEPTION 'mail secret refused' USING ERRCODE = '42501';
    END IF;
    RETURN vault.create_secret(p_secret, NULL, format('DINCR %s refresh token for account %s', p_provider, p_account_id));
END
$fn$;

CREATE OR REPLACE FUNCTION dincr_private.mail_secret_read(p_secret_id UUID, p_account_id UUID)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_description TEXT;
    v_secret TEXT;
BEGIN
    SELECT description, decrypted_secret INTO v_description, v_secret
    FROM vault.decrypted_secrets WHERE id = p_secret_id;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    IF NOT dincr_private.mail_secret_owned(v_description, p_account_id) THEN
        -- No identifiers in the message: it can reach logs.
        RAISE EXCEPTION 'mail secret belongs to another account' USING ERRCODE = '42501';
    END IF;
    RETURN v_secret;
END
$fn$;

CREATE OR REPLACE FUNCTION dincr_private.mail_secret_delete(p_secret_ids UUID[], p_account_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_deleted INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM vault.secrets s WHERE s.id = ANY(p_secret_ids)
               AND NOT dincr_private.mail_secret_owned(s.description, p_account_id)) THEN
        RAISE EXCEPTION 'mail secret belongs to another account' USING ERRCODE = '42501';
    END IF;
    DELETE FROM vault.secrets WHERE id = ANY(p_secret_ids);
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END
$fn$;

REVOKE ALL ON FUNCTION dincr_private.mail_secret_owned(TEXT, UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION dincr_private.mail_secret_create(TEXT, UUID, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION dincr_private.mail_secret_read(UUID, UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION dincr_private.mail_secret_delete(UUID[], UUID) FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON FUNCTION dincr_private.mail_secret_owned(TEXT, UUID) FROM anon, authenticated;
        REVOKE ALL ON FUNCTION dincr_private.mail_secret_create(TEXT, UUID, TEXT) FROM anon, authenticated;
        REVOKE ALL ON FUNCTION dincr_private.mail_secret_read(UUID, UUID) FROM anon, authenticated;
        REVOKE ALL ON FUNCTION dincr_private.mail_secret_delete(UUID[], UUID) FROM anon, authenticated;
    END IF;
END $$;

-- Every token a live connection or pending flow references must pass the check.
DO $$
DECLARE
    v_bad BIGINT := 0;
    v_count BIGINT;
BEGIN
    IF to_regclass('vault.secrets') IS NULL THEN
        RETURN;
    END IF;
    IF to_regclass('public.finva_gmail_connections') IS NOT NULL THEN
        SELECT count(*) INTO v_count FROM public.finva_gmail_connections c
        JOIN vault.secrets s ON s.id = c.refresh_token_secret_id
        WHERE NOT dincr_private.mail_secret_owned(s.description, c.account_id);
        v_bad := v_bad + v_count;
    END IF;
    IF to_regclass('public.mail_oauth_flows') IS NOT NULL THEN
        SELECT count(*) INTO v_count FROM public.mail_oauth_flows f
        JOIN vault.secrets s ON s.id = f.pending_secret_id
        WHERE NOT dincr_private.mail_secret_owned(s.description, f.account_id);
        v_bad := v_bad + v_count;
    END IF;
    IF v_bad > 0 THEN
        RAISE EXCEPTION '% mail tokens are not labelled with their account; resolve before applying', v_bad
            USING ERRCODE = 'APP02';
    END IF;
END $$;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'missing ' || f FROM unnest(ARRAY['dincr_private.mail_secret_create(text,uuid,text)',
--   'dincr_private.mail_secret_read(uuid,uuid)', 'dincr_private.mail_secret_delete(uuid[],uuid)']) f
--   WHERE to_regprocedure(f) IS NULL
-- UNION ALL SELECT 'public may run ' || p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--   WHERE n.nspname = 'dincr_private' AND has_function_privilege('public', p.oid, 'EXECUTE')
-- UNION ALL SELECT 'not security definer: ' || p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--   WHERE n.nspname = 'dincr_private' AND p.proname <> 'mail_secret_owned' AND NOT p.prosecdef;
