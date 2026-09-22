-- Cover the foreign keys introduced by Phase 1B. The workspace-first index is
-- retained for application reads; these two indexes support FK checks/deletes.

BEGIN;

CREATE INDEX IF NOT EXISTS idx_finva_candidates_financial_account_fk
    ON public.finva_email_candidates(financial_account_id)
    WHERE financial_account_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_finva_candidates_related_candidate_fk
    ON public.finva_email_candidates(related_candidate_id)
    WHERE related_candidate_id IS NOT NULL;

COMMIT;
