BEGIN;

CREATE TABLE IF NOT EXISTS finva_budget_items (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    monthly_limit NUMERIC(14,2) NOT NULL CHECK (monthly_limit >= 0),
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, category)
);

CREATE TABLE IF NOT EXISTS finva_recurring_items (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    category TEXT NOT NULL DEFAULT 'general',
    item_type TEXT NOT NULL DEFAULT 'expense' CHECK (item_type IN ('expense','income')),
    frequency TEXT NOT NULL DEFAULT 'monthly' CHECK (frequency IN ('weekly','biweekly','monthly','quarterly','annual')),
    due_day INTEGER CHECK (due_day BETWEEN 1 AND 31),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS finva_goal_contributions (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    goal_id BIGINT NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    contribution_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finva_recurring_workspace ON finva_recurring_items(workspace_id, is_active, due_day);
CREATE INDEX IF NOT EXISTS idx_finva_goal_contributions_workspace ON finva_goal_contributions(workspace_id, contribution_date);

INSERT INTO features(code,description) VALUES
    ('basic_dashboard','Dashboard financiero completo'),
    ('guided_budget','Presupuesto guiado'),
    ('financial_calendar','Calendario financiero'),
    ('recurring_items','Gastos recurrentes y suscripciones'),
    ('basic_reports','Reportes y estadísticas')
ON CONFLICT(code) DO UPDATE SET description=EXCLUDED.description;

INSERT INTO plan_features(plan_id,feature_id,enabled)
SELECT p.id,f.id,TRUE FROM plans p CROSS JOIN features f
WHERE p.code IN ('basic','vip')
  AND f.code IN ('basic_dashboard','guided_budget','financial_calendar','recurring_items','basic_reports')
ON CONFLICT(plan_id,feature_id) DO UPDATE SET enabled=TRUE;

COMMIT;
