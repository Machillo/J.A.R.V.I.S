-- Rollback of 20260926100000_plan_change_lifecycle.sql.
--
-- Drops the pending-change columns. Any scheduled downgrade is lost: those
-- accounts keep their current plan until its stored end and then follow the
-- default path (a still-paid plan, or Free), so no one loses access early.
-- The code keeps working without the columns (it refuses new downgrades of a
-- time-bounded plan with 409 instead of applying them immediately); restart the
-- backend after the rollback so it stops using its cached "columns present".
-- Rolling back only the code while keeping the columns is also safe: the old
-- code ignores them, but a later redeploy of this code would apply the pending
-- rows that are still there, so clear or review them first.
--
-- Run only under docs/security/migration-safety-protocol.md: BACKUP_VERIFIED
-- gate, a second reviewer, psql -v ON_ERROR_STOP=1 as the owner, one transaction.
-- Before running, record the scheduled changes that will be dropped:
--   SELECT count(*) FROM public.account_subscriptions WHERE pending_plan_id IS NOT NULL;

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

ALTER TABLE public.account_subscriptions DROP CONSTRAINT IF EXISTS ck_account_subscriptions_pending_complete;
ALTER TABLE public.account_subscriptions
    DROP COLUMN IF EXISTS pending_requested_at,
    DROP COLUMN IF EXISTS pending_effective_at,
    DROP COLUMN IF EXISTS pending_plan_id;

COMMIT;
