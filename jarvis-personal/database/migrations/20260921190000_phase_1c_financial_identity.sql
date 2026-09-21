-- Phase 1C: turn account_balances into FINVA's canonical financial identity.
-- Existing manually managed accounts remain confirmed as owned. Accounts
-- discovered from email start pending and never affect net worth automatically.

BEGIN;

ALTER TABLE public.account_balances
    ADD COLUMN IF NOT EXISTS account_id UUID REFERENCES public.accounts(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS institution_code TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS institution_country TEXT NOT NULL DEFAULT 'CR',
    ADD COLUMN IF NOT EXISTS ownership_status TEXT NOT NULL DEFAULT 'own',
    ADD COLUMN IF NOT EXISTS ownership_confirmed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS signals_count INTEGER NOT NULL DEFAULT 0;

UPDATE public.account_balances
SET institution_code = LOWER(REGEXP_REPLACE(COALESCE(bank_name, ''), '[^a-zA-Z0-9]+', '_', 'g')),
    ownership_confirmed_at = COALESCE(ownership_confirmed_at, created_at)
WHERE institution_code = '';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname='account_balances_ownership_status_check'
          AND conrelid='public.account_balances'::regclass
    ) THEN
        ALTER TABLE public.account_balances
            ADD CONSTRAINT account_balances_ownership_status_check
            CHECK (ownership_status IN ('pending', 'own', 'not_mine'));
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_finva_financial_identity
    ON public.account_balances(workspace_id, account_id, institution_code, account_last4, currency)
    WHERE account_id IS NOT NULL AND account_last4 IS NOT NULL AND account_last4 <> '';

CREATE INDEX IF NOT EXISTS idx_finva_financial_identity_owner_status
    ON public.account_balances(account_id, workspace_id, ownership_status, updated_at DESC)
    WHERE account_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_account_balances_account_fk
    ON public.account_balances(account_id)
    WHERE account_id IS NOT NULL;

REVOKE ALL ON TABLE public.account_balances FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.account_balances_id_seq FROM anon, authenticated;

COMMIT;
