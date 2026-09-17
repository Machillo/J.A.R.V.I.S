-- Shared preference onboarding for JARVIS and FINVA.
-- Existing financial profiles, plans, debts and movements are intentionally untouched.
ALTER TABLE public.accounts
    ADD COLUMN IF NOT EXISTS usage_goal TEXT,
    ADD COLUMN IF NOT EXISTS base_currency TEXT NOT NULL DEFAULT 'CRC',
    ADD COLUMN IF NOT EXISTS enabled_currencies TEXT[] NOT NULL DEFAULT ARRAY['CRC']::TEXT[],
    ADD COLUMN IF NOT EXISTS number_format TEXT NOT NULL DEFAULT 'dot_comma',
    ADD COLUMN IF NOT EXISTS currency_placement TEXT NOT NULL DEFAULT 'before',
    ADD COLUMN IF NOT EXISTS profile_setup_completed BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'accounts_usage_goal_check'
          AND conrelid = 'public.accounts'::regclass
    ) THEN
        ALTER TABLE public.accounts ADD CONSTRAINT accounts_usage_goal_check
        CHECK (usage_goal IS NULL OR usage_goal IN (
            'debt','save','partner','life_change','control','explore'
        ));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'accounts_base_currency_check'
          AND conrelid = 'public.accounts'::regclass
    ) THEN
        ALTER TABLE public.accounts ADD CONSTRAINT accounts_base_currency_check
        CHECK (base_currency IN ('CRC','USD','ARS','EUR','MXN','COP','GTQ','PAB'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'accounts_number_format_check'
          AND conrelid = 'public.accounts'::regclass
    ) THEN
        ALTER TABLE public.accounts ADD CONSTRAINT accounts_number_format_check
        CHECK (number_format IN ('dot_comma','comma_dot'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'accounts_enabled_currencies_check'
          AND conrelid = 'public.accounts'::regclass
    ) THEN
        ALTER TABLE public.accounts ADD CONSTRAINT accounts_enabled_currencies_check
        CHECK (
            cardinality(enabled_currencies) BETWEEN 1 AND 8
            AND enabled_currencies <@ ARRAY['CRC','USD','ARS','EUR','MXN','COP','GTQ','PAB']::TEXT[]
            AND base_currency = ANY(enabled_currencies)
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'accounts_currency_placement_check'
          AND conrelid = 'public.accounts'::regclass
    ) THEN
        ALTER TABLE public.accounts ADD CONSTRAINT accounts_currency_placement_check
        CHECK (currency_placement IN ('before','after'));
    END IF;
END $$;

COMMENT ON COLUMN public.accounts.usage_goal IS 'Primary self-declared reason for using JARVIS or FINVA.';
COMMENT ON COLUMN public.accounts.enabled_currencies IS 'Currencies the user wants available; base_currency must be included.';
