BEGIN;

ALTER TABLE debts ADD COLUMN IF NOT EXISTS start_date DATE;
ALTER TABLE debts ADD COLUMN IF NOT EXISTS first_payment_date DATE;
ALTER TABLE debts ADD COLUMN IF NOT EXISTS auto_update_monthly BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE debts ADD COLUMN IF NOT EXISTS installments_paid INTEGER NOT NULL DEFAULT 0;
ALTER TABLE debts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE debt_payments ADD COLUMN IF NOT EXISTS principal_amount NUMERIC(14,2);
ALTER TABLE debt_payments ADD COLUMN IF NOT EXISTS interest_amount NUMERIC(14,2);
ALTER TABLE debt_payments ADD COLUMN IF NOT EXISTS payment_date DATE;
ALTER TABLE debt_payments ADD COLUMN IF NOT EXISTS installment_number INTEGER;
ALTER TABLE debt_payments ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';

UPDATE debts
SET start_date = COALESCE(start_date, created_at::date)
WHERE start_date IS NULL;

UPDATE debts
SET first_payment_date = CASE
    WHEN make_date(
        EXTRACT(YEAR FROM start_date)::int,
        EXTRACT(MONTH FROM start_date)::int,
        LEAST(COALESCE(payment_day, EXTRACT(DAY FROM start_date)::int),
              EXTRACT(DAY FROM (date_trunc('month', start_date) + INTERVAL '1 month - 1 day'))::int)
    ) < start_date
    THEN (make_date(
        EXTRACT(YEAR FROM start_date)::int,
        EXTRACT(MONTH FROM start_date)::int,
        LEAST(COALESCE(payment_day, EXTRACT(DAY FROM start_date)::int),
              EXTRACT(DAY FROM (date_trunc('month', start_date) + INTERVAL '1 month - 1 day'))::int)
    ) + INTERVAL '1 month')::date
    ELSE make_date(
        EXTRACT(YEAR FROM start_date)::int,
        EXTRACT(MONTH FROM start_date)::int,
        LEAST(COALESCE(payment_day, EXTRACT(DAY FROM start_date)::int),
              EXTRACT(DAY FROM (date_trunc('month', start_date) + INTERVAL '1 month - 1 day'))::int)
    )
END
WHERE first_payment_date IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_debt_payments_unique_monthly_due
ON debt_payments(user_id, debt_id, payment_date)
WHERE payment_type = 'monthly_payment' AND payment_date IS NOT NULL;

COMMIT;
