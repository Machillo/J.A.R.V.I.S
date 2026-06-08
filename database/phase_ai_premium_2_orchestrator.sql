-- Fase IA Premium 2 - ChatGPT owner-only como router inteligente y panel de estrategia.
-- Seguro para ejecutar varias veces.

CREATE TABLE IF NOT EXISTS ai_premium_usage_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'openai',
    model TEXT NOT NULL,
    route TEXT NOT NULL DEFAULT 'jarvis',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_premium_guides (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    guide_type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_premium_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    monthly_budget_usd NUMERIC(12, 2) NOT NULL DEFAULT 10.00,
    warning_percent INTEGER NOT NULL DEFAULT 80,
    hard_stop_percent INTEGER NOT NULL DEFAULT 100,
    provider TEXT NOT NULL DEFAULT 'openai',
    model TEXT NOT NULL DEFAULT 'gpt-5-mini',
    owner_only BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_premium_usage_user_month ON ai_premium_usage_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_premium_guides_user ON ai_premium_guides(user_id, guide_type, is_active);

INSERT INTO ai_premium_settings (user_id, enabled, monthly_budget_usd, model, owner_only)
SELECT id, TRUE, 10.00, 'gpt-5-mini', TRUE
FROM allowed_users
WHERE role IN ('owner', 'admin')
ON CONFLICT (user_id)
DO UPDATE SET
    enabled = TRUE,
    monthly_budget_usd = 10.00,
    model = 'gpt-5-mini',
    owner_only = TRUE,
    updated_at = NOW();
