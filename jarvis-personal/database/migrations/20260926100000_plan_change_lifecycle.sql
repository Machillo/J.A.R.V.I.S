-- Scheduled plan changes: a downgrade or cancellation keeps the current plan
-- until its stored end (courtesy/promotion expires_at, or the paid period end).
--
-- account_subscriptions.pending_plan_id is the plan the account moves to at
-- pending_effective_at; the current plan_id keeps every benefit until then.
-- See backend/auth/plan_lifecycle.py.
--
-- Additive and idempotent: three nullable columns, one FK, one CHECK. No row is
-- rewritten (ADD COLUMN without a default is a catalog-only change). The code
-- runs before and after this migration: until it exists, a downgrade of a
-- time-bounded plan is refused (409), never applied immediately.
-- One transaction: apply it with backend/scripts/apply_migration.py
-- (BACKUP_VERIFIED gate), as the role that owns account_subscriptions (postgres).
-- The ALTER TABLE takes an ACCESS EXCLUSIVE lock on account_subscriptions until
-- COMMIT (milliseconds); logins wait on it, so apply at low traffic.
--
-- Preflight (read-only): must return zero rows.
--   SELECT 'missing: ' || t FROM unnest(ARRAY['account_subscriptions','plans']) t
--    WHERE to_regclass('public.' || t) IS NULL
--   UNION ALL
--   SELECT 'plans.id is not bigint' WHERE (SELECT format_type(atttypid, atttypmod) FROM pg_attribute
--    WHERE attrelid = 'public.plans'::regclass AND attname = 'id') <> 'bigint';
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926100000_plan_change_lifecycle_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

ALTER TABLE public.account_subscriptions
    ADD COLUMN IF NOT EXISTS pending_plan_id BIGINT REFERENCES public.plans(id),
    ADD COLUMN IF NOT EXISTS pending_effective_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pending_requested_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_account_subscriptions_pending_complete'
          AND conrelid = 'public.account_subscriptions'::regclass
    ) THEN
        -- A pending plan always has its effective date, and the reverse.
        ALTER TABLE public.account_subscriptions
            ADD CONSTRAINT ck_account_subscriptions_pending_complete
            CHECK ((pending_plan_id IS NULL) = (pending_effective_at IS NULL));
    END IF;
END $$;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'missing column: ' || c FROM unnest(ARRAY['pending_plan_id','pending_effective_at','pending_requested_at']) c
--  WHERE NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'public.account_subscriptions'::regclass
--                    AND attname = c AND NOT attisdropped)
-- UNION ALL
-- SELECT 'missing constraint: ck_account_subscriptions_pending_complete'
--  WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_account_subscriptions_pending_complete'
--                    AND conrelid = 'public.account_subscriptions'::regclass AND convalidated)
-- UNION ALL
-- SELECT 'missing FK: pending_plan_id -> plans'
--  WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE contype = 'f' AND conrelid = 'public.account_subscriptions'::regclass
--                    AND confrelid = 'public.plans'::regclass
--                    AND conkey = ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid = 'public.account_subscriptions'::regclass
--                                        AND attname = 'pending_plan_id')])
-- UNION ALL
-- SELECT 'unexpected pending rows right after the migration' FROM public.account_subscriptions
--  WHERE pending_plan_id IS NOT NULL HAVING count(*) > 0;
