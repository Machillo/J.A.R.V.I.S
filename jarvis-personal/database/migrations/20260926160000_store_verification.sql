-- Verified App Store / Google Play purchases: EXPAND phase (schema only).
--
-- A paid plan will come only from a purchase the store itself confirms (Apple signed
-- JWS, Google Play Developer API); the client's word is never enough. This adds the
-- structure only, backward compatible with the code on main, which never reads it:
-- - store_customer_tokens: one random token per DINCR account, sent to the store as
--   StoreKit appAccountToken / Play obfuscatedExternalAccountId, so a verified
--   purchase names the account it was bought for;
-- - store_purchases: the latest verified state of every purchase, keyed by the
--   store's stable identity (Apple originalTransactionId; Google the SHA-256 of the
--   purchase token, never the token itself). A purchase is bound to exactly one
--   account, forever: restoring it on another account is refused and logged;
-- - store_revocations: refunded or revoked store transactions, per transaction (a
--   single renewal can be refunded); kept even when the account is deleted;
-- - store_purchase_conflicts: a purchase presented for another account, for review;
-- - store_subscriptions gains grace_ends_at, revoked_at and environment (nullable).
-- No existing row is changed.
--
-- Nothing is granted: RLS is on and anon, authenticated and dincr_app have no
-- privilege on the new tables. The runtime role gets its grants and policies in the
-- activation migration that ships with the code using these tables, so that main
-- never grants dincr_app a table its code does not use (least privilege).
-- Meanwhile the tables are empty; the data export does not see them (it lists only
-- tables the role can access) and account deletion is unaffected (their foreign
-- keys to accounts CASCADE / SET NULL, run as the table owner).
--
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres.
-- Postflight: the query at the end of this file returns zero rows (before activation).
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

-- Supabase grants new public tables and sequences to its API roles by default. Each
-- role is revoked on its own, so a missing anon never leaves authenticated with access.
DO $$
DECLARE
    t TEXT;
    r TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM %I', t, r);
            END IF;
        END LOOP;
    END LOOP;
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE public.store_purchase_conflicts_id_seq FROM %I', r);
        END IF;
    END LOOP;
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
-- UNION ALL SELECT r || ' has ' || p || ' on ' || t
--   FROM unnest(ARRAY['store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations']) t,
--        unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r,
--        unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER']) p
--   WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) AND has_table_privilege(r, 'public.' || t, p)
-- UNION ALL SELECT r || ' has ' || p || ' on store_purchase_conflicts_id_seq'
--   FROM unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r, unnest(ARRAY['USAGE', 'SELECT', 'UPDATE']) p
--   WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
--     AND has_sequence_privilege(r, 'public.store_purchase_conflicts_id_seq', p)
-- UNION ALL SELECT 'policy ' || policyname || ' on ' || tablename FROM pg_policies
--   WHERE schemaname = 'public'
--     AND tablename IN ('store_customer_tokens', 'store_purchases', 'store_purchase_conflicts', 'store_revocations');
