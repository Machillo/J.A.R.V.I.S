-- Rollback of 20261021170000_mail_maintenance_pg_cron.sql: stops the scheduled mail maintenance.
--
-- Removes only what the migration added: the two jobs and their functions. The extensions stay installed
-- (dropping pg_net would also drop its recent responses; drop them by hand only if nothing else
-- uses them). The two Vault secrets are removed by the Owner in the dashboard if no longer wanted.
-- Mail, candidates and transactions are not touched. GitHub's scheduler keeps working meanwhile.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'dincr-mail-maintenance') THEN
        PERFORM cron.unschedule('dincr-mail-maintenance');
    END IF;
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'dincr-mail-maintenance-prune') THEN
        PERFORM cron.unschedule('dincr-mail-maintenance-prune');
    END IF;
END $$;

DROP FUNCTION IF EXISTS dincr_private.run_mail_maintenance();
DROP FUNCTION IF EXISTS dincr_private.prune_mail_maintenance_runs();

COMMIT;
