-- MANUAL rollback of 20261010120000_debt_monthly_payment_known.sql.
-- Human decision only; never run automatically.
--
-- Precondition: production no longer runs a backend that reads or writes
-- debts.monthly_payment_known (roll the unknown-payment code back first). Otherwise debt creation,
-- editing, the debts list and the VIP command center fail.
--
-- What it does: no payment changes. Only the knowledge of which payments were given
-- leaves `debts`; it is kept first in a closed snapshot table, as evidence and for a later
-- restore. Without the column, a 0 can again not be told from an unknown payment. Dropping a
-- column is catalog-only: no table rewrite.
--
-- How to run it (apply_migration.py refuses files outside database/migrations, and
-- docs/security/migration-safety-protocol.md §2 allows this exception):
--   1. BACKUP_VERIFIED gate open for this database (db_backup_verify.py gate);
--   2. a second person reads this file and the reason for rolling back;
--   3. psql -v ON_ERROR_STOP=1 over a direct session connection as postgres,
--      one transaction (this file's BEGIN/COMMIT).
-- Idempotent: a second run finds nothing left to snapshot or drop.
--
-- Postflight (read-only): must return zero rows.
--   SELECT column_name FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'debts' AND column_name = 'monthly_payment_known';

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

CREATE TABLE IF NOT EXISTS public.debt_monthly_payment_known_rollback_snapshot (
    debt_id BIGINT PRIMARY KEY,  -- debts.id (its workspace stays on the debt row)
    monthly_payment NUMERIC(14, 2),
    monthly_payment_known BOOLEAN NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.debt_monthly_payment_known_rollback_snapshot ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    -- Closed to the Data API, like every table the app itself does not expose.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.debt_monthly_payment_known_rollback_snapshot FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.debt_monthly_payment_known_rollback_snapshot FROM authenticated;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_attribute
               WHERE attrelid = 'public.debts'::regclass AND attname = 'monthly_payment_known' AND NOT attisdropped) THEN
        INSERT INTO public.debt_monthly_payment_known_rollback_snapshot (debt_id, monthly_payment, monthly_payment_known)
        SELECT id, monthly_payment, monthly_payment_known FROM public.debts
        WHERE monthly_payment_known IS NOT NULL
        ON CONFLICT (debt_id) DO UPDATE
            SET monthly_payment = EXCLUDED.monthly_payment, monthly_payment_known = EXCLUDED.monthly_payment_known,
                snapshot_at = NOW();
    END IF;
END $$;

ALTER TABLE public.debts DROP COLUMN IF EXISTS monthly_payment_known;

COMMIT;
