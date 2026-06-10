-- JARVIS finance intelligence modules: receivables, real balances and constraints.
CREATE TABLE IF NOT EXISTS receivables (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    person_name TEXT NOT NULL,
    original_amount NUMERIC(14, 2) NOT NULL,
    paid_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    pending_amount NUMERIC(14, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT receivables_amounts_non_negative CHECK (original_amount >= 0 AND paid_amount >= 0 AND pending_amount >= 0),
    CONSTRAINT receivables_status_check CHECK (status IN ('pending', 'partial', 'completed'))
);

CREATE TABLE IF NOT EXISTS receivable_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL,
    source_transaction_id BIGINT REFERENCES transactions(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT receivable_payments_amount_positive CHECK (amount > 0)
);

CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    account_name TEXT NOT NULL,
    bank_name TEXT,
    account_last4 TEXT,
    currency TEXT NOT NULL DEFAULT 'CRC',
    current_balance NUMERIC(14, 2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_receivables_user_id ON receivables(user_id);
CREATE INDEX IF NOT EXISTS idx_receivable_payments_user_id ON receivable_payments(user_id);
CREATE INDEX IF NOT EXISTS idx_account_balances_user_id ON account_balances(user_id);

INSERT INTO account_balances (user_id, account_name, bank_name, account_last4, currency, current_balance)
SELECT 1, 'BAC Planilla', 'BAC', '2572', 'CRC', 0
WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE user_id = 1 AND account_last4 = '2572');

INSERT INTO account_balances (user_id, account_name, bank_name, account_last4, currency, current_balance)
SELECT 1, 'BAC Cuenta', 'BAC', '8137', 'CRC', 0
WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE user_id = 1 AND account_last4 = '8137');

INSERT INTO account_balances (user_id, account_name, bank_name, account_last4, currency, current_balance)
SELECT 1, 'MultiMoney Colones', 'MultiMoney', '6126', 'CRC', 0
WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE user_id = 1 AND account_last4 = '6126');
