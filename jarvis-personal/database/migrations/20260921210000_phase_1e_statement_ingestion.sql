-- Phase 1E: private statement-document metadata and canonical statement candidates.
-- Raw PDF bytes and extracted full text are deliberately not persisted here.

BEGIN;

CREATE TABLE IF NOT EXISTS public.finva_statement_documents (
    id BIGSERIAL PRIMARY KEY,
    email_message_id BIGINT NOT NULL UNIQUE
        REFERENCES public.finva_email_messages(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    bank TEXT NOT NULL,
    statement_month TEXT,
    attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    document_hash TEXT NOT NULL,
    parser_name TEXT NOT NULL DEFAULT 'finva_statement',
    parser_version TEXT NOT NULL DEFAULT '1',
    movements_found INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','candidates_ready','empty','unsupported','failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.finva_email_candidates
    ADD COLUMN IF NOT EXISTS statement_document_id BIGINT
        REFERENCES public.finva_statement_documents(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_finva_statement_documents_owner
    ON public.finva_statement_documents(account_id, workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_finva_statement_documents_workspace_hash
    ON public.finva_statement_documents(workspace_id, document_hash);
CREATE INDEX IF NOT EXISTS idx_finva_candidates_statement_document_fk
    ON public.finva_email_candidates(statement_document_id)
    WHERE statement_document_id IS NOT NULL;

ALTER TABLE public.finva_statement_documents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.finva_statement_documents FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.finva_statement_documents_id_seq FROM anon, authenticated;

COMMIT;
