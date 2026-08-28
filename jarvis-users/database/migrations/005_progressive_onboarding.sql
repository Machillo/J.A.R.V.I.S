-- JARVIS Users: progressive onboarding by personal plan.
-- Run once in the JARVIS Users Supabase project only.

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS onboarding_level TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='profiles_onboarding_level_check'
    ) THEN
        ALTER TABLE profiles
            ADD CONSTRAINT profiles_onboarding_level_check
            CHECK (onboarding_level IS NULL OR onboarding_level IN ('free','basic','vip'));
    END IF;
END $$;

ALTER TABLE financial_profiles
    ADD COLUMN IF NOT EXISTS essential_monthly_expenses NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS liquid_savings NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS emergency_fund_target NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS strategy_preference TEXT,
    ADD COLUMN IF NOT EXISTS discretionary_monthly_minimum NUMERIC(14,2);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='financial_profiles_essential_expenses_check'
    ) THEN
        ALTER TABLE financial_profiles
            ADD CONSTRAINT financial_profiles_essential_expenses_check
            CHECK (essential_monthly_expenses IS NULL OR essential_monthly_expenses >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='financial_profiles_liquid_savings_check'
    ) THEN
        ALTER TABLE financial_profiles
            ADD CONSTRAINT financial_profiles_liquid_savings_check
            CHECK (liquid_savings IS NULL OR liquid_savings >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='financial_profiles_emergency_target_check'
    ) THEN
        ALTER TABLE financial_profiles
            ADD CONSTRAINT financial_profiles_emergency_target_check
            CHECK (emergency_fund_target IS NULL OR emergency_fund_target >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='financial_profiles_strategy_preference_check'
    ) THEN
        ALTER TABLE financial_profiles
            ADD CONSTRAINT financial_profiles_strategy_preference_check
            CHECK (strategy_preference IS NULL OR strategy_preference IN ('debt','emergency','goals','balanced'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='financial_profiles_discretionary_minimum_check'
    ) THEN
        ALTER TABLE financial_profiles
            ADD CONSTRAINT financial_profiles_discretionary_minimum_check
            CHECK (discretionary_monthly_minimum IS NULL OR discretionary_monthly_minimum >= 0);
    END IF;
END $$;

-- Existing users already completed the original income/pay onboarding, which now
-- corresponds to the Free information level. Basic/VIP users are asked only for
-- the new information their plan needs; no financial history is deleted.
UPDATE profiles
SET onboarding_level='free'
WHERE onboarding_completed=TRUE AND onboarding_level IS NULL;

UPDATE profiles p
SET onboarding_completed=FALSE, updated_at=NOW()
FROM subscriptions s
JOIN plans pl ON pl.id=s.plan_id
WHERE s.user_id=p.id
  AND pl.code IN ('basic','vip')
  AND COALESCE(p.onboarding_level, 'free')='free';
