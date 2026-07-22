BEGIN;

ALTER TABLE debts
    ADD COLUMN IF NOT EXISTS first_payment_date DATE,
    ADD COLUMN IF NOT EXISTS auto_update_monthly BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS installments_paid INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE debt_payments
    ADD COLUMN IF NOT EXISTS principal_amount NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS interest_amount NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS payment_date DATE,
    ADD COLUMN IF NOT EXISTS installment_number INTEGER,
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';

UPDATE debt_payments
SET payment_date = COALESCE(payment_date, created_at::date),
    principal_amount = COALESCE(principal_amount, GREATEST(previous_remaining_amount - new_remaining_amount, 0)),
    interest_amount = COALESCE(interest_amount, GREATEST(amount - GREATEST(previous_remaining_amount - new_remaining_amount, 0), 0)),
    source = COALESCE(NULLIF(source, ''), 'manual')
WHERE payment_date IS NULL
   OR principal_amount IS NULL
   OR interest_amount IS NULL
   OR source IS NULL
   OR source = '';

WITH numbered AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY debt_id ORDER BY payment_date, created_at, id) AS installment_number
    FROM debt_payments
    WHERE payment_type = 'monthly_payment'
)
UPDATE debt_payments p
SET installment_number = n.installment_number
FROM numbered n
WHERE p.id = n.id
  AND p.installment_number IS NULL;

UPDATE debts d
SET installments_paid = GREATEST(
        COALESCE((
            SELECT COUNT(*)::int
            FROM debt_payments p
            WHERE p.debt_id = d.id
              AND p.payment_type = 'monthly_payment'
        ), 0),
        CASE
            WHEN COALESCE(d.monthly_payment, 0) > 0 AND COALESCE(d.total_amount, 0) > COALESCE(d.remaining_amount, 0)
            THEN FLOOR((d.total_amount - d.remaining_amount) / d.monthly_payment)::int
            ELSE 0
        END
    ),
    first_payment_date = COALESCE(
        d.first_payment_date,
        CASE
            WHEN COALESCE(d.payment_day, 0) BETWEEN 1 AND 28 THEN
                CASE
                    WHEN make_date(EXTRACT(YEAR FROM d.created_at)::int, EXTRACT(MONTH FROM d.created_at)::int, d.payment_day) >= d.created_at::date
                    THEN make_date(EXTRACT(YEAR FROM d.created_at)::int, EXTRACT(MONTH FROM d.created_at)::int, d.payment_day)
                    ELSE (make_date(EXTRACT(YEAR FROM d.created_at)::int, EXTRACT(MONTH FROM d.created_at)::int, 1) + INTERVAL '1 month' + (d.payment_day - 1) * INTERVAL '1 day')::date
                END
            ELSE d.created_at::date
        END
    ),
    updated_at = NOW();

CREATE INDEX IF NOT EXISTS idx_debt_monthly_payment_date
ON debt_payments (debt_id, payment_date)
WHERE payment_type = 'monthly_payment' AND payment_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_debts_auto_update
ON debts (user_id, auto_update_monthly, first_payment_date);

COMMIT;
