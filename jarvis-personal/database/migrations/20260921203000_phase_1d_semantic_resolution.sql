-- Phase 1D: auditable semantic deduplication and confirmed own-account transfers.

BEGIN;

ALTER TABLE public.finva_email_candidates
    ADD COLUMN IF NOT EXISTS semantic_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS resolution_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_finva_candidates_semantic_fingerprint
    ON public.finva_email_candidates(workspace_id, semantic_fingerprint, created_at DESC)
    WHERE semantic_fingerprint IS NOT NULL;

COMMENT ON COLUMN public.finva_email_candidates.semantic_fingerprint IS
    'Conservative source-independent movement fingerprint; intentionally non-unique.';
COMMENT ON COLUMN public.finva_email_candidates.resolution_reason IS
    'Auditable reason for duplicate or internal-transfer resolution.';

REVOKE ALL ON TABLE public.finva_email_candidates FROM anon, authenticated;

COMMIT;
