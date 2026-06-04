-- Phase 2 hardening: multi-user data isolation integrity.
-- Run this in Supabase SQL Editor.
-- It does not delete data.

ALTER TABLE allowed_users
ADD COLUMN IF NOT EXISTS supabase_user_id TEXT;

ALTER TABLE allowed_users
ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_allowed_users_email ON allowed_users(email);
CREATE INDEX IF NOT EXISTS idx_allowed_users_supabase_user_id ON allowed_users(supabase_user_id);

INSERT INTO allowed_users (email, role, status, created_at)
VALUES ('gatotico99@gmail.com', 'owner', 'active', NOW())
ON CONFLICT (email)
DO UPDATE SET
    role = 'owner',
    status = 'active';


ALTER TABLE events
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'events'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE events
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE events
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE events
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE events
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);

ALTER TABLE logs
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'logs'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE logs
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE logs
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE logs
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE logs
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs(user_id);

ALTER TABLE salaries
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'salaries'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE salaries
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE salaries
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE salaries
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE salaries
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_salaries_user_id ON salaries(user_id);

ALTER TABLE bonuses
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'bonuses'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE bonuses
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE bonuses
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE bonuses
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE bonuses
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_bonuses_user_id ON bonuses(user_id);

ALTER TABLE debts
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'debts'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE debts
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE debts
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE debts
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE debts
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_debts_user_id ON debts(user_id);

ALTER TABLE debt_payments
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'debt_payments'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE debt_payments
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE debt_payments
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE debt_payments
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE debt_payments
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_debt_payments_user_id ON debt_payments(user_id);

ALTER TABLE savings
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'savings'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE savings
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE savings
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE savings
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE savings
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_savings_user_id ON savings(user_id);

ALTER TABLE investments
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'investments'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE investments
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE investments
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE investments
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE investments
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_investments_user_id ON investments(user_id);

ALTER TABLE expenses
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'expenses'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE expenses
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE expenses
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE expenses
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE expenses
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);

ALTER TABLE employment_profile
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'employment_profile'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE employment_profile
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE employment_profile
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE employment_profile
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE employment_profile
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_employment_profile_user_id ON employment_profile(user_id);

ALTER TABLE payroll_deductions
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payroll_deductions'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE payroll_deductions
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE payroll_deductions
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE payroll_deductions
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE payroll_deductions
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payroll_deductions_user_id ON payroll_deductions(user_id);

ALTER TABLE payroll_events
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payroll_events'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE payroll_events
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE payroll_events
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE payroll_events
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE payroll_events
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payroll_events_user_id ON payroll_events(user_id);

ALTER TABLE financial_goals
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'financial_goals'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE financial_goals
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE financial_goals
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE financial_goals
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE financial_goals
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_financial_goals_user_id ON financial_goals(user_id);

ALTER TABLE payment_schedules
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payment_schedules'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE payment_schedules
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE payment_schedules
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE payment_schedules
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE payment_schedules
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payment_schedules_user_id ON payment_schedules(user_id);

ALTER TABLE pay_schedule
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pay_schedule'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE pay_schedule
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE pay_schedule
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE pay_schedule
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE pay_schedule
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pay_schedule_user_id ON pay_schedule(user_id);

ALTER TABLE credit_card_settings
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'credit_card_settings'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE credit_card_settings
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE credit_card_settings
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE credit_card_settings
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE credit_card_settings
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_credit_card_settings_user_id ON credit_card_settings(user_id);

ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'transactions'
          AND column_name = 'user_id'
          AND data_type <> 'bigint'
    ) THEN
        ALTER TABLE transactions
        ALTER COLUMN user_id TYPE BIGINT
        USING CASE
            WHEN user_id::text ~ '^[0-9]+$' THEN user_id::text::BIGINT
            ELSE 1
        END;
    END IF;
END $$;

UPDATE transactions
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE transactions
ALTER COLUMN user_id SET DEFAULT 1;

ALTER TABLE transactions
ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);


-- Keep debt_payments.user_id aligned with the owner of the debt when possible.
UPDATE debt_payments dp
SET user_id = d.user_id
FROM debts d
WHERE dp.debt_id = d.id;

CREATE INDEX IF NOT EXISTS idx_debt_payments_debt_id ON debt_payments(debt_id);

-- Verification: should return every sensitive table with user_id BIGINT.
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND column_name = 'user_id'
ORDER BY table_name;
