-- Cover workspace deletion checks for the Email Monitor consent ledger.

CREATE INDEX IF NOT EXISTS idx_finva_gmail_consents_workspace_fk
    ON public.finva_gmail_consents(workspace_id);
