-- Phase 1F: opt-in AI fallback and privacy-safe parser feedback metrics.

BEGIN;

ALTER TABLE public.finva_gmail_connections
    ADD COLUMN IF NOT EXISTS ai_fallback_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ai_fallback_consent_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.finva_parser_fallback_events (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    email_message_id BIGINT REFERENCES public.finva_email_messages(id) ON DELETE SET NULL,
    candidate_id BIGINT REFERENCES public.finva_email_candidates(id) ON DELETE SET NULL,
    bank TEXT NOT NULL,
    format_fingerprint TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'google',
    model TEXT NOT NULL,
    outcome TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL DEFAULT 0,
    input_chars INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
    review_outcome TEXT,
    corrected_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    CONSTRAINT finva_parser_fallback_outcome_check
        CHECK (outcome IN ('candidate','not_confident','unavailable','error')),
    CONSTRAINT finva_parser_fallback_review_check
        CHECK (review_outcome IS NULL OR review_outcome IN ('accepted','corrected','rejected')),
    CONSTRAINT finva_parser_fallback_confidence_check
        CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX IF NOT EXISTS idx_finva_parser_fallback_workspace_created
    ON public.finva_parser_fallback_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_finva_parser_fallback_account_created
    ON public.finva_parser_fallback_events(account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_finva_parser_fallback_candidate
    ON public.finva_parser_fallback_events(candidate_id)
    WHERE candidate_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_finva_parser_fallback_fingerprint
    ON public.finva_parser_fallback_events(bank, format_fingerprint, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_finva_parser_fallback_message
    ON public.finva_parser_fallback_events(email_message_id)
    WHERE email_message_id IS NOT NULL;

ALTER TABLE public.finva_parser_fallback_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.finva_parser_fallback_events FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON SEQUENCE public.finva_parser_fallback_events_id_seq FROM anon, authenticated;

COMMIT;
