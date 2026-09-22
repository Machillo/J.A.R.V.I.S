BEGIN;

CREATE INDEX IF NOT EXISTS idx_financial_input_events_account_fk
    ON public.financial_input_events(account_id);
CREATE INDEX IF NOT EXISTS idx_financial_input_events_user_fk
    ON public.financial_input_events(user_id);

COMMIT;
