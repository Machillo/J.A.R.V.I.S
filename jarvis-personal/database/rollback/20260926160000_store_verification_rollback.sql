-- Rollback of 20260926160000_store_verification.sql.
--
-- PRE-ROLLBACK GATE: the code that verifies store purchases is reverted first, and
-- no table holds a row a human still needs: store_purchases (which account each paid
-- purchase belongs to), store_revocations (refunds; losing them makes a refunded
-- receipt claimable again) and store_purchase_conflicts. Export them before dropping.
-- Aborts (SV001) if any of them has a row, so paid history is never dropped blindly.
-- BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF (to_regclass('public.store_purchases') IS NOT NULL AND EXISTS (SELECT 1 FROM public.store_purchases))
       OR (to_regclass('public.store_revocations') IS NOT NULL AND EXISTS (SELECT 1 FROM public.store_revocations))
       OR (to_regclass('public.store_purchase_conflicts') IS NOT NULL
           AND EXISTS (SELECT 1 FROM public.store_purchase_conflicts)) THEN
        RAISE EXCEPTION 'store purchase history exists; export and decide before rolling back'
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
