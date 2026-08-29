BEGIN;

ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS access_source TEXT NOT NULL DEFAULT 'self_service',
    ADD COLUMN IF NOT EXISTS courtesy_note TEXT,
    ADD COLUMN IF NOT EXISTS granted_by TEXT,
    ADD COLUMN IF NOT EXISTS granted_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'subscriptions_access_source_check'
          AND conrelid = 'subscriptions'::regclass
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_access_source_check
            CHECK (access_source IN ('self_service', 'courtesy'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_subscriptions_courtesy_expiry
    ON subscriptions(expires_at)
    WHERE access_source='courtesy' AND status='active';

COMMIT;

SELECT
    COUNT(*) FILTER (WHERE access_source='courtesy') AS courtesy_subscriptions,
    COUNT(*) FILTER (
        WHERE access_source='courtesy'
          AND status='active'
          AND expires_at IS NOT NULL
          AND expires_at <= NOW()
    ) AS expired_courtesy_still_marked_active
FROM subscriptions;
