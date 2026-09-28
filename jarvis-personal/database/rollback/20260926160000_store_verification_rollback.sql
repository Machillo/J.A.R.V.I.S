-- Rollback of 20260926160000_store_verification.sql (expand phase: schema only).
--
-- Removes only what 160000 added: the four store_* tables and the three nullable
-- store_subscriptions columns. Nothing that existed before 160000 is touched.
--
-- PRE-ROLLBACK GATE:
-- - the activation (grants and policies for dincr_app) is rolled back first: aborts
--   (SV003) while dincr_app still has any privilege on the new tables;
-- - no table holds a row a human still needs: store_purchases (which account each
--   paid purchase belongs to), store_revocations (refunds; losing them makes a
--   refunded receipt claimable again), store_purchase_conflicts, store_customer_tokens,
--   and no store_subscriptions row uses the new columns. Export them before dropping.
--   Aborts (SV001) otherwise, so paid history is never dropped blindly.
-- BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    t TEXT;
    has_rows BOOLEAN;
BEGIN
    FOREACH t IN ARRAY ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations'] LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app')
               AND (has_table_privilege('dincr_app', 'public.' || t, 'SELECT')
                    OR has_table_privilege('dincr_app', 'public.' || t, 'INSERT')
                    OR has_table_privilege('dincr_app', 'public.' || t, 'UPDATE')
                    OR has_table_privilege('dincr_app', 'public.' || t, 'DELETE')) THEN
                RAISE EXCEPTION 'dincr_app still has privileges on %; roll back the activation first', t
                    USING ERRCODE = 'SV003';
            END IF;
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM public.%I)', t) INTO has_rows;
            IF has_rows THEN
                RAISE EXCEPTION 'store purchase history exists in %; export and decide before rolling back', t
                    USING ERRCODE = 'SV001';
            END IF;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'store_subscriptions' AND column_name = 'environment')
       AND EXISTS (SELECT 1 FROM public.store_subscriptions
                   WHERE grace_ends_at IS NOT NULL OR revoked_at IS NOT NULL OR environment IS NOT NULL) THEN
        RAISE EXCEPTION 'store_subscriptions rows use the new columns; export and decide before rolling back'
            USING ERRCODE = 'SV001';
    END IF;
END $$;

DROP TABLE IF EXISTS public.store_purchase_conflicts;
DROP TABLE IF EXISTS public.store_revocations;
DROP TABLE IF EXISTS public.store_purchases;
DROP TABLE IF EXISTS public.store_customer_tokens;
ALTER TABLE public.store_subscriptions
    DROP COLUMN IF EXISTS grace_ends_at,
    DROP COLUMN IF EXISTS revoked_at,
    DROP COLUMN IF EXISTS environment;

COMMIT;
