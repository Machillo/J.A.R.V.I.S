-- J.A.R.V.I.S admin + AI usage limits
-- Ejecutar en Supabase SQL Editor si querés crear las tablas antes del primer uso.

UPDATE allowed_users
SET role = 'owner', status = 'active'
WHERE lower(email) = 'gatotico99@gmail.com';

CREATE TABLE IF NOT EXISTS ai_usage_daily (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    usage_date DATE NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    response_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    requests_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, usage_date)
);

CREATE TABLE IF NOT EXISTS ai_usage_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    usage_date DATE NOT NULL,
    route TEXT,
    model TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    response_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_usage_limits (
    id BIGSERIAL PRIMARY KEY,
    role TEXT NOT NULL UNIQUE,
    daily_token_limit INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO ai_usage_limits (role, daily_token_limit)
VALUES
('owner', 250000),
('admin', 80000),
('user', 12000),
('viewer', 3000)
ON CONFLICT (role) DO UPDATE SET
    daily_token_limit = EXCLUDED.daily_token_limit,
    updated_at = NOW();
