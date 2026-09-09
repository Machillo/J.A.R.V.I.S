ALTER TABLE financial_goals
    ADD COLUMN IF NOT EXISTS goal_type TEXT NOT NULL DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS alternative_group TEXT,
    ADD COLUMN IF NOT EXISTS is_selected BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS funding_order INTEGER NOT NULL DEFAULT 100,
    ADD COLUMN IF NOT EXISTS depends_on_group TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_goals_selected_alternative
ON financial_goals(workspace_id, alternative_group)
WHERE alternative_group IS NOT NULL AND is_selected = TRUE AND status IN ('active', 'candidate');

CREATE INDEX IF NOT EXISTS idx_financial_goals_strategy_order
ON financial_goals(workspace_id, status, funding_order, target_date);
