BEGIN;

ALTER TABLE salaries ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'Salario';

CREATE TABLE IF NOT EXISTS finva_goal_contributions (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    goal_id BIGINT NOT NULL REFERENCES financial_goals(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    contribution_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finva_goal_contributions_workspace
    ON finva_goal_contributions(workspace_id, contribution_date);

COMMIT;
