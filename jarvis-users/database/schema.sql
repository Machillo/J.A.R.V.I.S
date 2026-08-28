-- JARVIS Users - clean SaaS baseline
-- Fresh installations should execute this file once in Supabase SQL Editor.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS profiles (
    id BIGSERIAL PRIMARY KEY,
    supabase_user_id UUID NOT NULL UNIQUE,
    account_id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin', 'owner')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'blocked')),
    onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    onboarding_level TEXT CHECK (onboarding_level IS NULL OR onboarding_level IN ('free','basic','vip')),
    plan_selected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS owner_personal_links (
    id BIGSERIAL PRIMARY KEY,
    users_profile_id BIGINT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
    personal_supabase_user_id UUID NOT NULL UNIQUE,
    personal_allowed_user_id BIGINT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_profiles (
    user_id BIGINT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    income_type TEXT NOT NULL CHECK (income_type IN ('fixed', 'hourly')),
    fixed_monthly_salary NUMERIC(14,2) CHECK (fixed_monthly_salary > 0),
    hourly_rate NUMERIC(14,2) CHECK (hourly_rate > 0),
    work_days_per_week INTEGER NOT NULL CHECK (work_days_per_week BETWEEN 1 AND 7),
    hours_per_day NUMERIC(6,2) CHECK (hours_per_day > 0 AND hours_per_day <= 24),
    pay_frequency TEXT NOT NULL CHECK (pay_frequency IN ('weekly', 'biweekly', 'monthly')),
    payday_note TEXT,
    essential_monthly_expenses NUMERIC(14,2) CHECK (essential_monthly_expenses IS NULL OR essential_monthly_expenses >= 0),
    liquid_savings NUMERIC(14,2) CHECK (liquid_savings IS NULL OR liquid_savings >= 0),
    emergency_fund_target NUMERIC(14,2) CHECK (emergency_fund_target IS NULL OR emergency_fund_target >= 0),
    strategy_preference TEXT CHECK (strategy_preference IS NULL OR strategy_preference IN ('debt','emergency','goals','balanced')),
    discretionary_monthly_minimum NUMERIC(14,2) CHECK (discretionary_monthly_minimum IS NULL OR discretionary_monthly_minimum >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((income_type='fixed' AND fixed_monthly_salary IS NOT NULL AND hourly_rate IS NULL)
        OR (income_type='hourly' AND hourly_rate IS NOT NULL AND hours_per_day IS NOT NULL AND fixed_monthly_salary IS NULL))
);

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
    user_id BIGINT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
    plan_id BIGINT NOT NULL REFERENCES plans(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'expired', 'suspended')),
    started_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    last_payment_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO plans (code, name)
VALUES ('free', 'Gratis'), ('basic', 'Basic'), ('vip', 'VIP')
ON CONFLICT (code) DO NOTHING;

INSERT INTO features (code, description) VALUES
    ('finance_overview', 'Resumen financiero'),
    ('spending', 'Ingresos y gastos'),
    ('debts', 'Deudas'),
    ('strategy_basic', 'Estrategia básica determinística'),
    ('goals', 'Metas'),
    ('transactions', 'Transacciones'),
    ('overtime', 'Horas extra'),
    ('strategy_vip', 'Dirección financiera dinámica VIP'),
    ('projections', 'Proyecciones y escenarios financieros'),
    ('smart_goals', 'Metas coordinadas con estrategia')
ON CONFLICT (code) DO NOTHING;

INSERT INTO plan_features (plan_id, feature_id, enabled)
SELECT p.id, f.id, TRUE
FROM plans p
JOIN features f ON (
    (p.code='free' AND f.code IN ('finance_overview','spending','debts','goals','transactions','overtime')) OR
    (p.code='basic' AND f.code IN ('finance_overview','spending','debts','goals','transactions','overtime','strategy_basic')) OR
    (p.code='vip')
)
WHERE p.code IN ('free','basic','vip')
ON CONFLICT (plan_id, feature_id) DO UPDATE SET enabled = TRUE;

CREATE TABLE IF NOT EXISTS income_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS overtime_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    hours NUMERIC(8,2) NOT NULL CHECK (hours > 0),
    hourly_rate NUMERIC(14,2) NOT NULL CHECK (hourly_rate > 0),
    multiplier NUMERIC(8,4) NOT NULL DEFAULT 1.5 CHECK (multiplier > 0),
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    work_date DATE NOT NULL DEFAULT CURRENT_DATE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    total_amount NUMERIC(14,2) CHECK (total_amount > 0),
    remaining_amount NUMERIC(14,2) NOT NULL CHECK (remaining_amount >= 0),
    monthly_payment NUMERIC(14,2) CHECK (monthly_payment >= 0),
    interest_rate NUMERIC(8,4) CHECK (interest_rate >= 0),
    payment_day INTEGER CHECK (payment_day BETWEEN 1 AND 31),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    debt_id BIGINT NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    payment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target_amount NUMERIC(14,2) NOT NULL CHECK (target_amount > 0),
    current_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (current_amount >= 0),
    target_date DATE,
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'paused')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    transaction_date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
    category TEXT NOT NULL DEFAULT 'general',
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_income_entries_user_date ON income_entries(user_id, entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, expense_date DESC);
CREATE INDEX IF NOT EXISTS idx_overtime_user_date ON overtime_entries(user_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_debts_user ON debts(user_id);
CREATE INDEX IF NOT EXISTS idx_debt_payments_user_debt ON debt_payments(user_id, debt_id);
CREATE INDEX IF NOT EXISTS idx_goals_user ON financial_goals(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, transaction_date DESC);
