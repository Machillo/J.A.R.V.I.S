-- JARVIS Users - SaaS identity foundation
-- Apply ONLY to the separate JARVIS Users Supabase project.
-- Do not run this migration against JARVIS Personal.

BEGIN;

-- Fresh Users installations should use database/schema.sql. This migration is
-- intentionally defensive for a Users database previously created from the old snapshot.
DO $$
BEGIN
    IF to_regclass('public.profiles') IS NULL AND to_regclass('public.allowed_users') IS NOT NULL THEN
        ALTER TABLE allowed_users RENAME TO profiles;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'allowed_user_id'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'profile_id'
    ) THEN
        ALTER TABLE users RENAME COLUMN allowed_user_id TO profile_id;
    END IF;
END $$;

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS display_name TEXT,
    ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE profiles
    ALTER COLUMN supabase_user_id TYPE UUID USING NULLIF(supabase_user_id, '')::uuid,
    ALTER COLUMN status SET DEFAULT 'active';

-- A SaaS profile must be tied to a real Supabase Auth identity.
-- If this fails, clean legacy placeholder profiles in the Users database first.
ALTER TABLE profiles
    ALTER COLUMN supabase_user_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_profiles_supabase_user_id ON profiles(supabase_user_id);

CREATE TABLE IF NOT EXISTS plans (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS features (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plan_features (
    plan_id BIGINT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    feature_id BIGINT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (plan_id, feature_id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    plan_id BIGINT NOT NULL REFERENCES plans(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'expired', 'suspended')),
    started_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    last_payment_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id)
);

INSERT INTO plans (code, name)
VALUES ('basic', 'Basic'), ('premium', 'Premium')
ON CONFLICT (code) DO NOTHING;

INSERT INTO features (code, description) VALUES
    ('finance_overview', 'Finance / Overview'),
    ('spending', 'Spending'),
    ('debts', 'Debts'),
    ('strategy_basic', 'Strategy Basic'),
    ('goals', 'Goals'),
    ('transactions', 'Transactions'),
    ('income', 'Registro de ingresos'),
    ('expenses', 'Registro de gastos'),
    ('overtime', 'Registro de horas extra'),
    ('chat_basic', 'JARVIS Chat limitado')
ON CONFLICT (code) DO NOTHING;

INSERT INTO plan_features (plan_id, feature_id, enabled)
SELECT p.id, f.id, TRUE
FROM plans p
CROSS JOIN features f
WHERE p.code = 'basic'
ON CONFLICT (plan_id, feature_id) DO NOTHING;

-- Critical SaaS invariant: never silently assign tenant 1.
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT table_schema, table_name
        FROM information_schema.columns
        WHERE column_name = 'user_id'
          AND table_schema = 'public'
          AND column_default IS NOT NULL
          AND column_default::text IN ('1', '1::bigint', '''1''::bigint')
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ALTER COLUMN user_id DROP DEFAULT', r.table_schema, r.table_name);
    END LOOP;
END $$;

COMMIT;
