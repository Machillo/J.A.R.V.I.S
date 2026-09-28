-- Rollback of 20260926161000_store_verification_activation.sql.
--
-- Takes back from dincr_app only what 161000 gave: the table privileges and the id
-- sequence USAGE on the four store_* tables, and their dincr_app_access policies.
-- No table, column or row is touched: the schema of 160000 and its data stay, so this
-- loses nothing and can be re-applied by applying 161000 again.
--
-- PRE-ROLLBACK GATE: DINCR_STORE_VERIFICATION_ENABLED is unset (or not "1") on every
-- backend service first. With the switch on, store requests would then fail with
-- "permission denied" instead of the controlled 503.
-- BACKUP_VERIFIED and a second reviewer, as for any migration.
-- Postflight after this rollback: the postflight of 20260926160000 returns zero rows.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    t TEXT;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RETURN;
    END IF;
    FOREACH t IN ARRAY ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations'] LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            EXECUTE format('DROP POLICY IF EXISTS dincr_app_access ON public.%I', t);
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM dincr_app', t);
        END IF;
    END LOOP;
    IF to_regclass('public.store_purchase_conflicts_id_seq') IS NOT NULL THEN
        REVOKE ALL PRIVILEGES ON SEQUENCE public.store_purchase_conflicts_id_seq FROM dincr_app;
    END IF;
END $$;

COMMIT;
