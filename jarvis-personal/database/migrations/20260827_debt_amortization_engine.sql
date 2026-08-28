BEGIN;

ALTER TABLE debts
    ADD COLUMN IF NOT EXISTS next_payment_date DATE,
    ADD COLUMN IF NOT EXISTS last_payment_date DATE,
    ADD COLUMN IF NOT EXISTS interest_method TEXT NOT NULL DEFAULT 'monthly',
    ADD COLUMN IF NOT EXISTS fixed_fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0;

ALTER TABLE debt_payments
    ADD COLUMN IF NOT EXISTS fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS extra_principal_amount NUMERIC(14,2) NOT NULL DEFAULT 0;

-- ---------------------------------------------------------------------------
-- Synchronize current debts with the real documents supplied in Aug-2026.
-- The existing remaining_amount values are treated as trusted balance anchors.
-- ---------------------------------------------------------------------------

-- Préstamo Papá: 15% nominal annual, 60 installments, payment day 10.
-- Current stored balance already includes the historical extra ₡50,000 payment.
UPDATE debts
SET interest_rate = 15.00,
    term_months = 60,
    payment_day = 10,
    start_date = DATE '2025-02-27',
    first_payment_date = DATE '2025-03-10',
    installments_paid = GREATEST(COALESCE(installments_paid, 0), 15),
    last_payment_date = COALESCE(last_payment_date, DATE '2026-05-10'),
    next_payment_date = COALESCE(next_payment_date, DATE '2026-06-10'),
    interest_method = 'monthly',
    fixed_fee_amount = 4309.52,
    auto_update_monthly = TRUE,
    updated_at = NOW()
WHERE user_id = 1 AND id = 1;

-- Banco Popular: official Jul-2026 statement.
UPDATE debts
SET total_amount = 3100000.00,
    remaining_amount = 2982694.80,
    monthly_payment = 65478.40,
    interest_rate = 19.50,
    term_months = 108,
    payment_day = 9,
    start_date = DATE '2025-09-09',
    first_payment_date = DATE '2025-10-09',
    installments_paid = 10,
    last_payment_date = DATE '2026-07-09',
    next_payment_date = DATE '2026-08-09',
    interest_method = 'daily_365',
    fixed_fee_amount = 4390.85,
    auto_update_monthly = TRUE,
    updated_at = NOW()
WHERE user_id = 1 AND id = 2 AND COALESCE(installments_paid, 0) <= 10;

-- BAC Extrafinanciamiento (OLE): payment includes monthly insurance.
UPDATE debts
SET remaining_amount = 491636.63,
    monthly_payment = 16953.65,
    interest_rate = 26.00,
    term_months = 60,
    payment_day = 5,
    first_payment_date = DATE '2026-07-05',
    installments_paid = 2,
    last_payment_date = DATE '2026-08-21',
    next_payment_date = DATE '2026-09-05',
    interest_method = 'monthly',
    fixed_fee_amount = 1983.45,
    auto_update_monthly = TRUE,
    updated_at = NOW()
WHERE user_id = 1 AND id = 3 AND COALESCE(installments_paid, 0) <= 2;

-- Reloj / iShop tasa cero.
UPDATE debts
SET remaining_amount = 148072.73,
    monthly_payment = 7793.30,
    first_payment_date = DATE '2026-04-05',
    interest_rate = 0,
    term_months = 24,
    installments_paid = 5,
    last_payment_date = DATE '2026-08-21',
    next_payment_date = DATE '2026-09-05',
    interest_method = 'monthly',
    fixed_fee_amount = 0,
    auto_update_monthly = TRUE,
    updated_at = NOW()
WHERE user_id = 1 AND id = 4 AND COALESCE(installments_paid, 0) <= 5;

-- BAC Minicuota.
UPDATE debts
SET remaining_amount = 61542.82,
    monthly_payment = 8759.77,
    first_payment_date = DATE '2026-05-05',
    interest_rate = 35.76,
    term_months = 12,
    installments_paid = 4,
    last_payment_date = DATE '2026-08-21',
    next_payment_date = DATE '2026-09-05',
    interest_method = 'monthly',
    fixed_fee_amount = 0,
    auto_update_monthly = TRUE,
    updated_at = NOW()
WHERE user_id = 1 AND id = 5 AND COALESCE(installments_paid, 0) <= 4;

-- Finished BAC installment plans.
UPDATE debts
SET remaining_amount = 0,
    installments_paid = term_months,
    next_payment_date = NULL,
    interest_method = 'monthly',
    fixed_fee_amount = 0,
    auto_update_monthly = FALSE,
    updated_at = NOW()
WHERE user_id = 1 AND id IN (6, 7);

-- MultiMoney current ₡400k draw. Existing 2.90 represented monthly rate;
-- store the equivalent annual nominal rate used by the contract model.
UPDATE debts
SET total_amount = 400000.00,
    remaining_amount = LEAST(COALESCE(remaining_amount, 400000.00), 400000.00),
    monthly_payment = 20500.00,
    interest_rate = 34.80,
    term_months = 60,
    payment_day = 1,
    start_date = DATE '2026-07-30',
    first_payment_date = DATE '2026-09-01',
    interest_method = 'daily_365',
    fixed_fee_amount = 0,
    auto_update_monthly = TRUE,
    updated_at = NOW()
WHERE user_id = 1 AND id = 8;

COMMIT;
