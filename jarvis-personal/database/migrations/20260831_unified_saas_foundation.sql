BEGIN;

ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS onboarding_level TEXT,
    ADD COLUMN IF NOT EXISTS plan_selected BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname='accounts_onboarding_level_check'
          AND conrelid='accounts'::regclass
    ) THEN
        ALTER TABLE accounts
            ADD CONSTRAINT accounts_onboarding_level_check
            CHECK (onboarding_level IS NULL OR onboarding_level IN ('free','basic','vip'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS plans (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS features (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plan_features (
    plan_id BIGINT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    feature_id BIGINT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (plan_id, feature_id)
);

CREATE TABLE IF NOT EXISTS account_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
    plan_id BIGINT NOT NULL REFERENCES plans(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('pending','active','expired','suspended')),
    access_source TEXT NOT NULL DEFAULT 'self_service' CHECK (access_source IN ('self_service','courtesy','owner')),
    started_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    last_payment_at TIMESTAMPTZ,
    courtesy_note TEXT,
    granted_by UUID REFERENCES accounts(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_account_subscriptions_expiry
    ON account_subscriptions(expires_at)
    WHERE status='active' AND expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS financial_profiles (
    account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    income_type TEXT NOT NULL CHECK (income_type IN ('fixed','hourly')),
    fixed_monthly_salary NUMERIC(14,2) CHECK (fixed_monthly_salary IS NULL OR fixed_monthly_salary > 0),
    hourly_rate NUMERIC(14,2) CHECK (hourly_rate IS NULL OR hourly_rate > 0),
    work_days_per_week INTEGER NOT NULL CHECK (work_days_per_week BETWEEN 1 AND 7),
    hours_per_day NUMERIC(6,2) CHECK (hours_per_day IS NULL OR (hours_per_day > 0 AND hours_per_day <= 24)),
    pay_frequency TEXT NOT NULL CHECK (pay_frequency IN ('weekly','biweekly','monthly')),
    payday_note TEXT,
    essential_monthly_expenses NUMERIC(14,2) CHECK (essential_monthly_expenses IS NULL OR essential_monthly_expenses >= 0),
    liquid_savings NUMERIC(14,2) CHECK (liquid_savings IS NULL OR liquid_savings >= 0),
    emergency_fund_target NUMERIC(14,2) CHECK (emergency_fund_target IS NULL OR emergency_fund_target >= 0),
    strategy_preference TEXT CHECK (strategy_preference IS NULL OR strategy_preference IN ('debt','emergency','goals','balanced')),
    discretionary_monthly_minimum NUMERIC(14,2) CHECK (discretionary_monthly_minimum IS NULL OR discretionary_monthly_minimum >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_profiles_workspace ON financial_profiles(workspace_id);

INSERT INTO plans(code,name) VALUES
    ('free','Gratis'),('basic','Basic'),('vip','VIP')
ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name, is_active=TRUE;

INSERT INTO features(code,description) VALUES
    ('finance_overview','Resumen financiero'),
    ('spending','Ingresos y gastos'),
    ('debts','Deudas'),
    ('goals','Metas'),
    ('transactions','Transacciones'),
    ('overtime','Horas extra'),
    ('strategy_basic','Estrategia determinística Basic'),
    ('strategy_vip','Dirección financiera dinámica VIP'),
    ('projections','Proyecciones y escenarios'),
    ('smart_goals','Metas coordinadas con estrategia')
ON CONFLICT(code) DO UPDATE SET description=EXCLUDED.description;

INSERT INTO plan_features(plan_id,feature_id,enabled)
SELECT p.id,f.id,TRUE
FROM plans p
JOIN features f ON (
    (p.code='free' AND f.code IN ('finance_overview','spending','debts','goals','transactions','overtime')) OR
    (p.code='basic' AND f.code IN ('finance_overview','spending','debts','goals','transactions','overtime','strategy_basic')) OR
    (p.code='vip')
)
WHERE p.code IN ('free','basic','vip')
ON CONFLICT(plan_id,feature_id) DO UPDATE SET enabled=TRUE;

-- Kenneth/owner retains full access and never enters commercial onboarding.
INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,created_at,updated_at)
SELECT a.id,p.id,'active','owner',NOW(),NOW(),NOW()
FROM accounts a CROSS JOIN plans p
WHERE a.role='owner' AND p.code='vip'
ON CONFLICT(account_id) DO UPDATE SET
    plan_id=EXCLUDED.plan_id,status='active',access_source='owner',expires_at=NULL,updated_at=NOW();

UPDATE accounts
SET plan_selected=TRUE,
    onboarding_completed=TRUE,
    onboarding_level='vip',
    updated_at=NOW()
WHERE role='owner';

-- Existing non-owner accounts start safely on Free if they had no subscription.
INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,created_at,updated_at)
SELECT a.id,p.id,'active','self_service',NOW(),NOW(),NOW()
FROM accounts a CROSS JOIN plans p
WHERE a.role<>'owner' AND p.code='free'
ON CONFLICT(account_id) DO NOTHING;

COMMIT;

SELECT
    (SELECT COUNT(*) FROM accounts) AS accounts_total,
    (SELECT COUNT(*) FROM account_subscriptions) AS subscriptions_total,
    (SELECT COUNT(*) FROM accounts a LEFT JOIN account_subscriptions s ON s.account_id=a.id WHERE s.id IS NULL) AS accounts_without_subscription,
    (SELECT COUNT(*) FROM workspaces w LEFT JOIN workspace_members wm ON wm.workspace_id=w.id AND wm.account_id=w.owner_account_id WHERE wm.id IS NULL) AS owner_workspaces_without_membership;
