-- JARVIS Users cleanup migration
-- Intended for the current development Users database before onboarding is implemented.
-- It preserves identity/subscription tables and removes modules copied from JARVIS Personal.

BEGIN;

-- Remove legacy/personal tables. Current development financial data in these tables is intentionally discarded.
DROP TABLE IF EXISTS business_movements CASCADE;
DROP TABLE IF EXISTS business_projects CASCADE;
DROP TABLE IF EXISTS investment_portfolio_snapshots CASCADE;
DROP TABLE IF EXISTS investment_cashflows CASCADE;
DROP TABLE IF EXISTS email_parser_logs CASCADE;
DROP TABLE IF EXISTS card_aliases CASCADE;
DROP TABLE IF EXISTS notification_jobs CASCADE;
DROP TABLE IF EXISTS notification_subscriptions CASCADE;
DROP TABLE IF EXISTS email_statement_documents CASCADE;
DROP TABLE IF EXISTS email_transaction_candidates CASCADE;
DROP TABLE IF EXISTS email_ingested_messages CASCADE;
DROP TABLE IF EXISTS email_monitor_settings CASCADE;
DROP TABLE IF EXISTS fixed_expense_matches CASCADE;
DROP TABLE IF EXISTS fixed_expenses CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;
DROP TABLE IF EXISTS memory_items CASCADE;
DROP TABLE IF EXISTS chat_pending_actions CASCADE;
DROP TABLE IF EXISTS chat_sessions CASCADE;
DROP TABLE IF EXISTS category_catalog CASCADE;
DROP TABLE IF EXISTS receivable_entries CASCADE;
DROP TABLE IF EXISTS receivable_payments CASCADE;
DROP TABLE IF EXISTS receivables CASCADE;
DROP TABLE IF EXISTS exchange_rates CASCADE;
DROP TABLE IF EXISTS credit_card_settings CASCADE;
DROP TABLE IF EXISTS pay_schedule CASCADE;
DROP TABLE IF EXISTS payment_schedules CASCADE;
DROP TABLE IF EXISTS payroll_deductions CASCADE;
DROP TABLE IF EXISTS employment_profile CASCADE;
DROP TABLE IF EXISTS investments CASCADE;
DROP TABLE IF EXISTS savings CASCADE;
DROP TABLE IF EXISTS bonuses CASCADE;
DROP TABLE IF EXISTS salaries CASCADE;
DROP TABLE IF EXISTS logs CASCADE;
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS settings CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Recreate the small financial surface cleanly.
DROP TABLE IF EXISTS debt_payments CASCADE;
DROP TABLE IF EXISTS debts CASCADE;
DROP TABLE IF EXISTS financial_goals CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS overtime_entries CASCADE;
DROP TABLE IF EXISTS expenses CASCADE;
DROP TABLE IF EXISTS income_entries CASCADE;

DELETE FROM plan_features;
DELETE FROM features;

INSERT INTO features (code, description) VALUES
    ('finance_overview', 'Resumen financiero'),
    ('spending', 'Ingresos y gastos'),
    ('debts', 'Deudas'),
    ('strategy_basic', 'Estrategia básica determinística'),
    ('goals', 'Metas'),
    ('transactions', 'Transacciones'),
    ('overtime', 'Horas extra'),
    ('chat_basic', 'Chat JARVIS básico')
ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description;

INSERT INTO plan_features (plan_id, feature_id, enabled)
SELECT p.id, f.id, TRUE
FROM plans p CROSS JOIN features f
WHERE p.code = 'basic';

CREATE TABLE income_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE overtime_entries (
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
CREATE TABLE debts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL CHECK (total_amount > 0),
    remaining_amount NUMERIC(14,2) NOT NULL CHECK (remaining_amount >= 0),
    monthly_payment NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (monthly_payment >= 0),
    interest_rate NUMERIC(8,4) NOT NULL DEFAULT 0 CHECK (interest_rate >= 0),
    payment_day INTEGER CHECK (payment_day BETWEEN 1 AND 31),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE debt_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    debt_id BIGINT NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    payment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE financial_goals (
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
CREATE TABLE transactions (
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

CREATE INDEX idx_income_entries_user_date ON income_entries(user_id, entry_date DESC);
CREATE INDEX idx_expenses_user_date ON expenses(user_id, expense_date DESC);
CREATE INDEX idx_overtime_user_date ON overtime_entries(user_id, work_date DESC);
CREATE INDEX idx_debts_user ON debts(user_id);
CREATE INDEX idx_debt_payments_user_debt ON debt_payments(user_id, debt_id);
CREATE INDEX idx_goals_user ON financial_goals(user_id);
CREATE INDEX idx_transactions_user_date ON transactions(user_id, transaction_date DESC);

COMMIT;
