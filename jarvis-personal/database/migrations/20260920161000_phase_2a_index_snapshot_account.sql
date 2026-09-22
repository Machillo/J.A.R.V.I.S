-- FINVA Phase 2A: cover the account foreign key used for ownership checks and deletes.

CREATE INDEX IF NOT EXISTS idx_financial_state_snapshots_account
    ON public.financial_state_snapshots(account_id);
