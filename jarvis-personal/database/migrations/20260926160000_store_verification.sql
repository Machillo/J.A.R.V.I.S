-- Verified App Store / Google Play purchases.
--
-- A paid plan comes only from a purchase the store itself confirms (Apple signed
-- JWS, Google Play Developer API); the client's word is never enough. This adds:
-- - store_customer_tokens: one random token per DINCR account, sent to the store as
--   StoreKit appAccountToken / Play obfuscatedExternalAccountId, so a verified
--   purchase names the account it was bought for;
-- - store_purchases: the latest verified state of every purchase, keyed by the
--   store's stable identity (Apple originalTransactionId; Google the SHA-256 of the
--   purchase token, never the token itself). A purchase is bound to exactly one
--   account, forever: restoring it on another account is refused and logged;
-- - store_revocations: refunded or revoked store transactions, per transaction (a
--   single renewal can be refunded); kept even when the account is deleted;
-- - store_subscriptions gains grace_ends_at, revoked_at and environment. It becomes
--   the account's derived entitlement: the best currently active verified purchase
--   across both stores (backend/product_ops/store_state.py).
-- The Owner sandbox simulator's rows (provider 'sandbox') never grant a plan.
-- No existing row is changed.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres, BEFORE
-- the code of this PR is deployed.
--
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20260926160000_store_verification_rollback.sql.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

CREATE TABLE IF NOT EXISTS public.store_customer_tokens (
    account_id UUID PRIMARY KEY REFERENCES public.accounts(id) ON DELETE CASCADE,
    token UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.store_purchases (
    provider TEXT NOT NULL CHECK (provider IN ('apple', 'google')),
    purchase_key TEXT NOT NULL,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    environment TEXT NOT NULL CHECK (environment IN ('production', 'sandbox')),
    product_id TEXT NOT NULL,
    plan_code TEXT NOT NULL CHECK (plan_code IN ('basic', 'vip')),
    billing_period TEXT NOT NULL CHECK (billing_period IN ('monthly', 'annual')),
    status TEXT NOT NULL CHECK (status IN ('trialing', 'active', 'grace_period', 'expired', 'revoked', 'superseded')),
    auto_renew BOOLEAN NOT NULL DEFAULT FALSE,
    trial_ends_at TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    grace_ends_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    pending_product_id TEXT,
    superseded_by TEXT,
    -- The store transaction (Apple transactionId, Google order id) this state describes,
    -- and its version: a state from an older transaction never replaces a newer one.
    last_transaction_id TEXT NOT NULL,
    state_version BIGINT NOT NULL,
    -- When the store signed or produced this state (Apple signedDate, Google API read):
    -- a late retry about the same transaction never replaces a newer state of it.
    observed_version BIGINT NOT NULL DEFAULT 0,
    last_verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, purchase_key)
);
CREATE INDEX IF NOT EXISTS idx_store_purchases_account ON public.store_purchases(account_id);

-- Refunded / revoked store transactions (one renewal can be refunded without the
-- subscription). No link to an account: the record outlives an account deletion, so a
-- refunded purchase can never be claimed again by presenting its pre-refund receipt.
CREATE TABLE IF NOT EXISTS public.store_revocations (
    provider TEXT NOT NULL CHECK (provider IN ('apple', 'google')),
    transaction_id TEXT NOT NULL,
    purchase_key TEXT NOT NULL,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reversed_at TIMESTAMPTZ,
    PRIMARY KEY (provider, transaction_id)
);

-- A purchase restored or reported for another account than its own: kept for review.
CREATE TABLE IF NOT EXISTS public.store_purchase_conflicts (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    purchase_key TEXT NOT NULL,
    bound_account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
    claimed_account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.store_subscriptions
    ADD COLUMN IF NOT EXISTS grace_ends_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS environment TEXT;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated', t);
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL PRIVILEGES ON SEQUENCE public.store_purchase_conflicts_id_seq FROM anon, authenticated;
    END IF;
    -- The runtime role (20260926150000). Without it the new tables would be unreachable
    -- at runtime, so the migration aborts instead of skipping the grants.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dincr_app') THEN
        RAISE EXCEPTION 'role dincr_app is missing: apply 20260926150000 first' USING ERRCODE = 'SV002';
    ELSE
        EXECUTE 'GRANT SELECT, INSERT ON TABLE public.store_customer_tokens TO dincr_app';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.store_purchases TO dincr_app';
        EXECUTE 'GRANT SELECT, INSERT ON TABLE public.store_purchase_conflicts TO dincr_app';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.store_revocations TO dincr_app';
        EXECUTE 'GRANT USAGE ON SEQUENCE public.store_purchase_conflicts_id_seq TO dincr_app';
        -- One explicit policy per table (RLS is on; without it the role reads no rows).
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'store_customer_tokens'
                       AND policyname = 'dincr_app_access') THEN
            CREATE POLICY dincr_app_access ON public.store_customer_tokens AS PERMISSIVE FOR ALL TO dincr_app
                USING (true) WITH CHECK (true);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'store_purchases'
                       AND policyname = 'dincr_app_access') THEN
            CREATE POLICY dincr_app_access ON public.store_purchases AS PERMISSIVE FOR ALL TO dincr_app
                USING (true) WITH CHECK (true);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'store_purchase_conflicts'
                       AND policyname = 'dincr_app_access') THEN
            CREATE POLICY dincr_app_access ON public.store_purchase_conflicts AS PERMISSIVE FOR ALL TO dincr_app
                USING (true) WITH CHECK (true);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'store_revocations'
                       AND policyname = 'dincr_app_access') THEN
            CREATE POLICY dincr_app_access ON public.store_revocations AS PERMISSIVE FOR ALL TO dincr_app
                USING (true) WITH CHECK (true);
        END IF;
    END IF;
END $$;

COMMIT;

-- Postflight (read-only): must return zero rows.
-- SELECT 'missing ' || t FROM unnest(ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations']) t
--   WHERE to_regclass('public.' || t) IS NULL
-- UNION ALL SELECT 'missing column store_subscriptions.' || c FROM unnest(ARRAY['grace_ends_at', 'revoked_at', 'environment']) c
--   WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns
--                     WHERE table_schema = 'public' AND table_name = 'store_subscriptions' AND column_name = c)
-- UNION ALL SELECT 'row level security off on ' || relname FROM pg_class
--   WHERE relname IN ('store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations')
--     AND NOT relrowsecurity
-- UNION ALL SELECT 'dincr_app cannot ' || p || ' ' || t
--   FROM (VALUES ('store_customer_tokens', 'SELECT'), ('store_customer_tokens', 'INSERT'),
--                ('store_purchases', 'SELECT'), ('store_purchases', 'INSERT'), ('store_purchases', 'UPDATE'),
--                ('store_purchase_conflicts', 'SELECT'), ('store_purchase_conflicts', 'INSERT'),
--                ('store_revocations', 'SELECT'), ('store_revocations', 'INSERT'), ('store_revocations', 'UPDATE')) g(t, p)
--   WHERE NOT has_table_privilege('dincr_app', 'public.' || t, p)
-- UNION ALL SELECT 'missing policy dincr_app_access on ' || t
--   FROM unnest(ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations']) t
--   WHERE NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = t
--                     AND policyname = 'dincr_app_access' AND 'dincr_app' = ANY(roles));
