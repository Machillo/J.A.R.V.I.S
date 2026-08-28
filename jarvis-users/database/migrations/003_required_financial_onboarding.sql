-- JARVIS Users: required financial onboarding.
-- Run once in the JARVIS Users Supabase project only.

CREATE TABLE IF NOT EXISTS financial_profiles (
    user_id BIGINT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    income_type TEXT NOT NULL CHECK (income_type IN ('fixed', 'hourly')),
    fixed_monthly_salary NUMERIC(14,2) CHECK (fixed_monthly_salary > 0),
    hourly_rate NUMERIC(14,2) CHECK (hourly_rate > 0),
    work_days_per_week INTEGER NOT NULL CHECK (work_days_per_week BETWEEN 1 AND 7),
    hours_per_day NUMERIC(6,2) CHECK (hours_per_day > 0 AND hours_per_day <= 24),
    pay_frequency TEXT NOT NULL CHECK (pay_frequency IN ('weekly', 'biweekly', 'monthly')),
    payday_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (income_type = 'fixed' AND fixed_monthly_salary IS NOT NULL AND hourly_rate IS NULL)
        OR
        (income_type = 'hourly' AND hourly_rate IS NOT NULL AND hours_per_day IS NOT NULL AND fixed_monthly_salary IS NULL)
    )
);

-- Unknown debt details must stay unknown (NULL), not masquerade as zero.
ALTER TABLE debts ALTER COLUMN total_amount DROP NOT NULL;
ALTER TABLE debts ALTER COLUMN monthly_payment DROP NOT NULL;
ALTER TABLE debts ALTER COLUMN monthly_payment DROP DEFAULT;
ALTER TABLE debts ALTER COLUMN interest_rate DROP NOT NULL;
ALTER TABLE debts ALTER COLUMN interest_rate DROP DEFAULT;

-- Existing test accounts intentionally remain onboarding_completed = FALSE.
-- Therefore both current accounts will be forced into onboarding on next login.
