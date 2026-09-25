-- Synthetic, production-shaped subset of the legacy financial tables used by the
-- ownership integrity tests. Applied after database/baseline/v1_identity_ownership.sql.
-- Workspace FKs are added later by the tests (NOT VALID), as Phase 2A did.

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
    start_date DATE,
    first_payment_date DATE,
    next_payment_date DATE,
    last_payment_date DATE,
    auto_update_monthly BOOLEAN NOT NULL DEFAULT TRUE,
    installments_paid INTEGER NOT NULL DEFAULT 0,
    interest_method TEXT NOT NULL DEFAULT 'monthly',
    fixed_fee_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    debt_id BIGINT NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    payment_type TEXT NOT NULL DEFAULT 'manual',
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID
);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    transaction_date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    transaction_type TEXT NOT NULL,
    category TEXT,
    account TEXT,
    source TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID
);

CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    category TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID
);

CREATE TABLE IF NOT EXISTS receivables (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    workspace_id UUID
);

CREATE TABLE IF NOT EXISTS receivable_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL,
    workspace_id UUID
);

CREATE TABLE IF NOT EXISTS financial_input_events (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    event_name TEXT NOT NULL DEFAULT 'transaction_confirmed'
);
