-- Phase 1B: enrich FINVA's review queue with a source-agnostic financial
-- candidate contract. Gmail is one producer; later statement/API adapters may
-- emit the same normalized shape without leaking provider details downstream.

BEGIN;

ALTER TABLE public.finva_email_candidates
    ADD COLUMN IF NOT EXISTS movement_index INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'email',
    ADD COLUMN IF NOT EXISTS source_provider TEXT NOT NULL DEFAULT 'gmail',
    ADD COLUMN IF NOT EXISTS source_record_key TEXT,
    ADD COLUMN IF NOT EXISTS institution_country TEXT NOT NULL DEFAULT 'CR',
    ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'CRC',
    ADD COLUMN IF NOT EXISTS original_amount NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS original_currency TEXT,
    ADD COLUMN IF NOT EXISTS transaction_time TIME,
    ADD COLUMN IF NOT EXISTS movement_direction TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS movement_kind TEXT NOT NULL DEFAULT 'other',
    ADD COLUMN IF NOT EXISTS source_account_label TEXT,
    ADD COLUMN IF NOT EXISTS source_account_reference TEXT,
    ADD COLUMN IF NOT EXISTS destination_account_reference TEXT,
    ADD COLUMN IF NOT EXISTS counterparty TEXT,
    ADD COLUMN IF NOT EXISTS external_reference TEXT,
    ADD COLUMN IF NOT EXISTS parser_name TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS parser_version TEXT NOT NULL DEFAULT '1',
    ADD COLUMN IF NOT EXISTS extraction_method TEXT NOT NULL DEFAULT 'parser',
    ADD COLUMN IF NOT EXISTS uncertainty_reason TEXT,
    ADD COLUMN IF NOT EXISTS dedupe_key TEXT,
    ADD COLUMN IF NOT EXISTS financial_account_id BIGINT
        REFERENCES public.account_balances(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS related_candidate_id BIGINT
        REFERENCES public.finva_email_candidates(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS is_internal_transfer BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS corrected_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

-- The original schema allowed only one movement per message. Statements and
-- compound notifications need multiple candidates while remaining idempotent.
ALTER TABLE public.finva_email_candidates
    DROP CONSTRAINT IF EXISTS finva_email_candidates_email_message_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_finva_candidates_message_movement
    ON public.finva_email_candidates(email_message_id, movement_index);

CREATE INDEX IF NOT EXISTS idx_finva_candidates_workspace_dedupe
    ON public.finva_email_candidates(workspace_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_finva_candidates_financial_account
    ON public.finva_email_candidates(workspace_id, financial_account_id, transaction_date DESC)
    WHERE financial_account_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'finva_candidates_source_type_check'
          AND conrelid = 'public.finva_email_candidates'::regclass
    ) THEN
        ALTER TABLE public.finva_email_candidates
            ADD CONSTRAINT finva_candidates_source_type_check
            CHECK (source_type IN ('email', 'statement', 'manual', 'api'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'finva_candidates_extraction_method_check'
          AND conrelid = 'public.finva_email_candidates'::regclass
    ) THEN
        ALTER TABLE public.finva_email_candidates
            ADD CONSTRAINT finva_candidates_extraction_method_check
            CHECK (extraction_method IN ('parser', 'ai', 'hybrid', 'manual'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'finva_candidates_direction_check'
          AND conrelid = 'public.finva_email_candidates'::regclass
    ) THEN
        ALTER TABLE public.finva_email_candidates
            ADD CONSTRAINT finva_candidates_direction_check
            CHECK (movement_direction IN ('in', 'out', 'internal', 'unknown'));
    END IF;
END $$;

COMMIT;
