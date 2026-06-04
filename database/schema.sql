CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    timezone TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS settings (
    id BIGSERIAL PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS allowed_users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    event_type TEXT NOT NULL,
    event_date TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS logs (
    id BIGSERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS salaries (
    id BIGSERIAL PRIMARY KEY,
    amount NUMERIC(14, 2) NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bonuses (
    id BIGSERIAL PRIMARY KEY,
    amount NUMERIC(14, 2) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    debt_type TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    remaining_amount NUMERIC(14, 2) NOT NULL,
    monthly_payment NUMERIC(14, 2) NOT NULL,
    interest_rate NUMERIC(8, 4),
    term_months INTEGER,
    payment_day INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id BIGSERIAL PRIMARY KEY,
    debt_id BIGINT NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    payment_type TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    previous_remaining_amount NUMERIC(14, 2) NOT NULL,
    new_remaining_amount NUMERIC(14, 2) NOT NULL,
    previous_monthly_payment NUMERIC(14, 2) NOT NULL,
    new_monthly_payment NUMERIC(14, 2) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS savings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS investments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    category TEXT NOT NULL,
    expense_type TEXT NOT NULL,
    description TEXT,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employment_profile (
    id BIGSERIAL PRIMARY KEY,
    hourly_rate NUMERIC(14, 2) NOT NULL,
    regular_hours_per_week NUMERIC(8, 2) NOT NULL,
    overtime_multiplier NUMERIC(8, 4) NOT NULL,
    holiday_multiplier NUMERIC(8, 4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payroll_deductions (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    deduction_type TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    frequency TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payroll_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    hours NUMERIC(8, 2) NOT NULL,
    multiplier NUMERIC(8, 4) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    target_amount NUMERIC(14, 2) NOT NULL,
    current_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    target_date TEXT,
    priority TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payment_schedules (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id BIGINT,
    payment_method TEXT NOT NULL,
    frequency TEXT NOT NULL,
    day_of_month INTEGER,
    cut_day INTEGER,
    payment_day INTEGER,
    auto_deducted BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pay_schedule (
    id BIGSERIAL PRIMARY KEY,
    pay_frequency TEXT NOT NULL,
    pay_day TEXT,
    first_pay_date TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS credit_card_settings (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    cut_day INTEGER NOT NULL,
    payment_day INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    transaction_date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    transaction_type TEXT NOT NULL,
    category TEXT NOT NULL,
    account TEXT,
    source TEXT,
    notes TEXT,
    original_amount NUMERIC(14, 2),
    original_currency TEXT,
    exchange_rate NUMERIC(14, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_debts_user_id ON debts(user_id);
CREATE INDEX IF NOT EXISTS idx_savings_user_id ON savings(user_id);
CREATE INDEX IF NOT EXISTS idx_investments_user_id ON investments(user_id);
CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_financial_goals_user_id ON financial_goals(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
