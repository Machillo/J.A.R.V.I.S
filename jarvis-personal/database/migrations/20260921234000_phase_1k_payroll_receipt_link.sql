-- Phase 1K: keep CCSS reported salary separate from a bank-confirmed payroll receipt.

BEGIN;

ALTER TABLE public.payroll_salary_reports
    ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'expected'
        CHECK (payment_status IN ('expected','received')),
    ADD COLUMN IF NOT EXISTS received_candidate_id BIGINT
        REFERENCES public.finva_email_candidates(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS received_at DATE;

CREATE INDEX IF NOT EXISTS idx_payroll_salary_reports_received_candidate_fk
    ON public.payroll_salary_reports(received_candidate_id)
    WHERE received_candidate_id IS NOT NULL;

COMMENT ON COLUMN public.payroll_salary_reports.payment_status IS
    'CCSS establishes expected/reported salary; only an explicit applied bank payroll credit changes this to received.';

ALTER TABLE public.payroll_salary_reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.payroll_salary_reports FROM anon, authenticated;

COMMIT;
