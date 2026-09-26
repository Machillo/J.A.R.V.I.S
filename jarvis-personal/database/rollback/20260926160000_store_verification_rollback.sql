-- Rollback of 20260926160000_store_verification.sql.
--
-- PRE-ROLLBACK GATE: the code that verifies store purchases is reverted first, and
-- store_purchases holds no row a human still needs (it is the record of which
-- account each paid purchase belongs to; export it before dropping). Aborts (SV001)
-- if any verified purchase exists, so paid history is never dropped blindly.
-- BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF to_regclass('public.store_purchases') IS NOT NULL AND EXISTS (SELECT 1 FROM public.store_purchases) THEN
        RAISE EXCEPTION 'store_purchases holds verified purchases; export and decide before rolling back'
            USING ERRCODE = 'SV001';
    END IF;
END $$;

DROP TABLE IF EXISTS public.store_purchase_conflicts;
DROP TABLE IF EXISTS public.store_purchases;
DROP TABLE IF EXISTS public.store_customer_tokens;
ALTER TABLE public.store_subscriptions
    DROP COLUMN IF EXISTS grace_ends_at,
    DROP COLUMN IF EXISTS revoked_at,
    DROP COLUMN IF EXISTS environment;

COMMIT;
