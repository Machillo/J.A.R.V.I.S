-- Mail maintenance scheduler inside Supabase (pg_cron + pg_net).
--
-- Why: POST /user-product/vip/gmail/maintenance reads every connected mailbox (Gmail and Outlook)
-- in the background. Its only scheduler was a GitHub Actions cron of every 10 minutes, which
-- GitHub runs every 2 to 5 hours in this repository, so new bank mail waited hours unless the app
-- was opened. pg_cron runs on the database's own clock; pg_net makes the call asynchronously.
--
-- What it does: every 10 minutes, dincr_private.run_mail_maintenance() queues one HTTPS POST to
-- the backend's maintenance endpoint with the cron secret in the X-Finva-Cron-Secret header.
-- The backend does all the work (plans, Owner automation, dedupe, watch renewal); nothing here
-- reads or writes mail, candidates or transactions.
--
-- Secrets: none in this file. Two Vault secrets, created by the Owner (dashboard → Vault) before
-- the job can call anything:
--   dincr_backend_url              the backend's base URL (https://…, no path)
--   dincr_mail_maintenance_secret  the same value as the backend's FINVA_GMAIL_CRON_SECRET
-- Until both exist the job fails on every run (visible in cron.job_run_details) instead of
-- succeeding silently.
--
-- Access: the function is SECURITY DEFINER (owner: postgres) with a fixed search_path and is
-- callable by nobody but its owner and pg_cron (EXECUTE revoked from PUBLIC, anon, authenticated
-- and the application role). It lives in dincr_private, which the Data API does not expose.
--
-- Requirements: Supabase project with the pg_cron and pg_net extensions available (both are, not
-- installed). Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, AFTER
-- the two Vault secrets exist. No application code depends on it.
--
-- Postflight (read-only):
--   SELECT jobname, schedule, active FROM cron.job WHERE jobname = 'dincr-mail-maintenance';
--   SELECT status, return_message, start_time FROM cron.job_run_details
--     WHERE jobid = (SELECT jobid FROM cron.job WHERE jobname = 'dincr-mail-maintenance')
--     ORDER BY start_time DESC LIMIT 5;
--   SELECT status_code, content::jsonb - 'retention' AS counts, created FROM net._http_response
--     ORDER BY created DESC LIMIT 5;   -- counts only; pg_net keeps responses for 6 hours
-- Rollback: database/rollback/20261021170000_mail_maintenance_pg_cron_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';

CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;  -- creates its own schema, net

CREATE SCHEMA IF NOT EXISTS dincr_private;
REVOKE ALL ON SCHEMA dincr_private FROM PUBLIC;

CREATE OR REPLACE FUNCTION dincr_private.run_mail_maintenance()
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_base_url TEXT;
    v_secret TEXT;
BEGIN
    SELECT decrypted_secret INTO v_base_url FROM vault.decrypted_secrets WHERE name = 'dincr_backend_url';
    SELECT decrypted_secret INTO v_secret FROM vault.decrypted_secrets WHERE name = 'dincr_mail_maintenance_secret';
    IF coalesce(v_base_url, '') !~ '^https://[^/?#\s]+/?$' OR coalesce(v_secret, '') = '' THEN
        -- Never a silent no-op: the run is recorded as failed until both Vault secrets exist.
        RAISE EXCEPTION 'mail maintenance not configured (Vault: dincr_backend_url, dincr_mail_maintenance_secret)'
            USING ERRCODE = '55000';
    END IF;
    -- Asynchronous: returns the pg_net request id at once; the backend may take minutes.
    RETURN net.http_post(
        url := rtrim(v_base_url, '/') || '/user-product/vip/gmail/maintenance',
        body := '{}'::jsonb,
        headers := jsonb_build_object('Content-Type', 'application/json', 'X-Finva-Cron-Secret', v_secret),
        timeout_milliseconds := 300000
    );
END
$fn$;

ALTER FUNCTION dincr_private.run_mail_maintenance() OWNER TO postgres;
REVOKE ALL ON FUNCTION dincr_private.run_mail_maintenance() FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON SCHEMA dincr_private FROM anon, authenticated;
        REVOKE ALL ON FUNCTION dincr_private.run_mail_maintenance() FROM anon, authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        REVOKE ALL ON FUNCTION dincr_private.run_mail_maintenance() FROM dincr_app;
    END IF;
END $$;

-- pg_cron never prunes cron.job_run_details: keep this job's last 7 days only (no other job's rows).
CREATE OR REPLACE FUNCTION dincr_private.prune_mail_maintenance_runs()
RETURNS VOID
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
    DELETE FROM cron.job_run_details
    WHERE jobid IN (SELECT jobid FROM cron.job WHERE jobname IN ('dincr-mail-maintenance', 'dincr-mail-maintenance-prune'))
      AND end_time < now() - interval '7 days'
$fn$;

ALTER FUNCTION dincr_private.prune_mail_maintenance_runs() OWNER TO postgres;
REVOKE ALL ON FUNCTION dincr_private.prune_mail_maintenance_runs() FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON FUNCTION dincr_private.prune_mail_maintenance_runs() FROM anon, authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        REVOKE ALL ON FUNCTION dincr_private.prune_mail_maintenance_runs() FROM dincr_app;
    END IF;
END $$;

-- Same name = same job: applying this again updates the schedule instead of adding a second one.
SELECT cron.schedule('dincr-mail-maintenance', '*/10 * * * *', 'SELECT dincr_private.run_mail_maintenance()');
SELECT cron.schedule('dincr-mail-maintenance-prune', '17 4 * * *', 'SELECT dincr_private.prune_mail_maintenance_runs()');

COMMIT;
