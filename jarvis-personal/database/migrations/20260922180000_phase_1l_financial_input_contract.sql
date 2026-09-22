BEGIN;

-- Phase 1's stable boundary. It intentionally contains only normalized
-- transaction facts; Gmail bodies, attachment text and parser evidence stay
-- in the retention-controlled ingestion tables.
CREATE TABLE IF NOT EXISTS public.financial_input_events (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES public.allowed_users(id) ON DELETE CASCADE,
    event_name TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    transaction_id BIGINT NOT NULL REFERENCES public.transactions(id) ON DELETE CASCADE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT financial_input_events_contract_check
        CHECK (event_name = 'transaction_confirmed' AND contract_version = 'financial-input-v1'),
    CONSTRAINT financial_input_events_payload_check
        CHECK (NOT (payload ?| ARRAY['raw_payload','body','attachment_text','sender','subject']))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_input_events_transaction_contract
    ON public.financial_input_events(transaction_id,event_name,contract_version);
CREATE INDEX IF NOT EXISTS idx_financial_input_events_workspace_created
    ON public.financial_input_events(workspace_id,created_at DESC);

ALTER TABLE public.financial_input_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.financial_input_events FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON SEQUENCE public.financial_input_events_id_seq FROM anon, authenticated;

COMMIT;
