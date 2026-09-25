-- Retire the off-store (SINPE Móvil) billing schema.
--
-- Product decision: DINCR takes public payments only through the App Store and
-- Google Play (store_subscriptions / store_subscription_events). The code no longer
-- reads or writes these tables (backend/test_security_contract.py forbids it).
--
-- Tables retired:
--   billing_orders        manual SINPE orders and uploaded receipts
--   billing_subscriptions off-store paid periods
--   finva_beta_programs   the retired paid-beta configuration row
--
-- Safety: aborts with SQLSTATE BL001, dropping nothing, unless billing_orders and
-- billing_subscriptions are EMPTY and finva_beta_programs holds at most its single
-- configuration row (no personal data). Production read-only, 2026-09-25: 0 orders,
-- 0 subscriptions, 1 configuration row.
-- Apply AFTER the code of this PR is deployed (the old code reads these tables),
-- with backend/scripts/apply_migration.py behind BACKUP_VERIFIED, as postgres.
--
-- Preflight (read-only): must return orders=0, subscriptions=0, beta_programs<=1.
--   SELECT (SELECT count(*) FROM public.billing_orders) AS orders,
--          (SELECT count(*) FROM public.billing_subscriptions) AS subscriptions,
--          (SELECT count(*) FROM public.finva_beta_programs) AS beta_programs;
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926120000_retire_offstore_billing_rollback.sql
--   (recreates the three tables empty; the configuration row is re-inserted).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

LOCK TABLE public.billing_orders, public.billing_subscriptions, public.finva_beta_programs IN ACCESS EXCLUSIVE MODE;

DO $$
DECLARE
    v_orders BIGINT;
    v_subscriptions BIGINT;
    v_programs BIGINT;
BEGIN
    SELECT count(*) INTO v_orders FROM public.billing_orders;
    SELECT count(*) INTO v_subscriptions FROM public.billing_subscriptions;
    SELECT count(*) INTO v_programs FROM public.finva_beta_programs;
    IF v_orders > 0 OR v_subscriptions > 0 OR v_programs > 1 THEN
        RAISE EXCEPTION 'off-store billing holds data (orders=%, subscriptions=%, programs=%); retire it by a reviewed plan',
            v_orders, v_subscriptions, v_programs USING ERRCODE = 'BL001';
    END IF;
END $$;

DROP TABLE public.billing_orders;
DROP TABLE public.billing_subscriptions;
DROP TABLE public.finva_beta_programs;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'still present: ' || t FROM unnest(ARRAY['billing_orders','billing_subscriptions','finva_beta_programs']) t
--  WHERE to_regclass('public.' || t) IS NOT NULL;
