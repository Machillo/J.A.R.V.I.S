-- SUPERSEDED by migrations/20260925130000_request_path_schema.sql. DO NOT APPLY.
-- Kept outside database/migrations so apply_migration.py refuses it. It creates
-- finva_goal_contributions without row level security, outside the replay
-- precondition of that migration, and takes an ACCESS EXCLUSIVE lock on
-- salaries. The newer migration creates the table closed to the Data API and
-- adds salaries.category only where it is missing (production already has it).
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
