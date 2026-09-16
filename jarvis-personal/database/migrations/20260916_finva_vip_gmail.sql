-- FINVA VIP Gmail connections. JARVIS Personal keeps its existing owner-only
-- email monitor; these tables belong only to the FINVA product flow.

BEGIN;

CREATE EXTENSION IF NOT EXISTS supabase_vault WITH SCHEMA vault;

CREATE TABLE IF NOT EXISTS public.finva_gmail_connections (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL UNIQUE REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    legacy_user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    google_email TEXT NOT NULL,
    refresh_token_secret_id UUID NOT NULL,
    granted_scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'reauthorization_required', 'disabled')),
    history_id TEXT,
    watch_expiration TIMESTAMPTZ,
    last_sync_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_error TEXT,
    connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, google_email)
);

CREATE TABLE IF NOT EXISTS public.finva_gmail_oauth_states (
    state_hash TEXT PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    legacy_user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.finva_email_messages (
    id BIGSERIAL PRIMARY KEY,
    connection_id BIGINT NOT NULL REFERENCES public.finva_gmail_connections(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    provider_message_id TEXT NOT NULL,
    sender TEXT,
    subject TEXT,
    received_at TIMESTAMPTZ,
    bank TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'processed',
    parse_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(connection_id, provider_message_id)
);

CREATE TABLE IF NOT EXISTS public.finva_email_candidates (
    id BIGSERIAL PRIMARY KEY,
    email_message_id BIGINT NOT NULL UNIQUE REFERENCES public.finva_email_messages(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    transaction_id BIGINT REFERENCES public.transactions(id) ON DELETE SET NULL,
    transaction_date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    transaction_type TEXT NOT NULL,
    category TEXT NOT NULL,
    bank TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'auto_saved', 'confirmed', 'rejected', 'duplicate')),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finva_gmail_email_status
    ON public.finva_gmail_connections(google_email, status);
CREATE INDEX IF NOT EXISTS idx_finva_email_candidates_workspace_status
    ON public.finva_email_candidates(workspace_id, status, created_at DESC);

ALTER TABLE public.finva_gmail_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finva_gmail_oauth_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finva_email_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finva_email_candidates ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE
    public.finva_gmail_connections,
    public.finva_gmail_oauth_states,
    public.finva_email_messages,
    public.finva_email_candidates
FROM anon, authenticated;

REVOKE ALL ON SEQUENCE
    public.finva_gmail_connections_id_seq,
    public.finva_email_messages_id_seq,
    public.finva_email_candidates_id_seq
FROM anon, authenticated;

COMMIT;
