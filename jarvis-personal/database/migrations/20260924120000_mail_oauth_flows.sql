-- Server-side OAuth flows for Gmail and Outlook mailbox connections.
--
-- A flow is started by an authenticated DINCR session, is single use, belongs
-- to one provider, expires after 10 minutes and only attaches a mailbox after
-- the same account/workspace redeems the one-time completion code delivered to
-- the app by deep link. Only hashes of the state and completion code are kept;
-- the refresh token stays in Supabase Vault (pending_secret_id) until then.
--
-- Rollback: DROP TABLE public.mail_oauth_flows;
-- (first delete any vault.secrets referenced by pending_secret_id)
BEGIN;

CREATE TABLE IF NOT EXISTS public.mail_oauth_flows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_hash TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL CHECK (provider IN ('gmail', 'microsoft')),
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'callback', 'authorized', 'completed', 'failed')),
    code_verifier TEXT,
    completion_hash TEXT,
    pending_secret_id UUID,
    mailbox_address TEXT,
    granted_scopes TEXT[],
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mail_oauth_flows_account ON public.mail_oauth_flows(account_id);
CREATE INDEX IF NOT EXISTS idx_mail_oauth_flows_workspace ON public.mail_oauth_flows(workspace_id);
CREATE INDEX IF NOT EXISTS idx_mail_oauth_flows_expires ON public.mail_oauth_flows(expires_at);

ALTER TABLE public.mail_oauth_flows ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.mail_oauth_flows FROM anon, authenticated;

COMMIT;
