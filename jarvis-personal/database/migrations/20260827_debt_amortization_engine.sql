BEGIN;

ALTER TABLE debts
    ADD COLUMN IF NOT EXISTS next_payment_date DATE,
    ADD COLUMN IF NOT EXISTS last_payment_date DATE,
    ADD COLUMN IF NOT EXISTS interest_method TEXT NOT NULL DEFAULT 'monthly',
    ADD COLUMN IF NOT EXISTS fixed_fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0;

ALTER TABLE debt_payments
    ADD COLUMN IF NOT EXISTS fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS extra_principal_amount NUMERIC(14,2) NOT NULL DEFAULT 0;

-- The account-specific balance corrections that lived here were applied to production on
-- their original date and removed from this file: real financial data does not belong in
-- the repository. The statements only matched one existing account, so a new database
-- is unaffected.

COMMIT;
