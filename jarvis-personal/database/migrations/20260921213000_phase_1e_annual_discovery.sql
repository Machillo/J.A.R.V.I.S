-- Phase 1E follow-up: persist self-declared institutions and resumable annual discovery.

BEGIN;

ALTER TABLE public.accounts
    ADD COLUMN IF NOT EXISTS selected_financial_institutions TEXT[]
        NOT NULL DEFAULT ARRAY[]::TEXT[];

ALTER TABLE public.finva_gmail_connections
    ADD COLUMN IF NOT EXISTS initial_scan_page_token TEXT,
    ADD COLUMN IF NOT EXISTS initial_scan_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS initial_scan_completed_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname='accounts_selected_financial_institutions_check'
          AND conrelid='public.accounts'::regclass
    ) THEN
        ALTER TABLE public.accounts
            ADD CONSTRAINT accounts_selected_financial_institutions_check
            CHECK (
                cardinality(selected_financial_institutions) <= 8
                AND selected_financial_institutions <@ ARRAY[
                    'bac','bn','bcr','popular','davivienda','scotiabank','promerica','multimoney'
                ]::TEXT[]
            );
    END IF;
END $$;

COMMIT;
