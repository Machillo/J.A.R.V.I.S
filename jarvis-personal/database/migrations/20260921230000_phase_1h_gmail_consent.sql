-- Phase 1H: explicit, versioned consent before FINVA authorizes Gmail access.

BEGIN;

CREATE TABLE IF NOT EXISTS public.finva_gmail_consents (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    consent_version TEXT NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id, workspace_id, consent_version)
);

CREATE INDEX IF NOT EXISTS idx_finva_gmail_consents_current
    ON public.finva_gmail_consents(account_id, workspace_id, consent_version)
    WHERE revoked_at IS NULL;

ALTER TABLE public.finva_gmail_consents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.finva_gmail_consents FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.finva_gmail_consents_id_seq FROM anon, authenticated;

COMMIT;
