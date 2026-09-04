-- JARVIS 06: daily, workspace-scoped net-worth history.
CREATE TABLE IF NOT EXISTS net_worth_snapshots (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    liquid_assets NUMERIC(18,2) NOT NULL DEFAULT 0,
    investments NUMERIC(18,2) NOT NULL DEFAULT 0,
    assets_total NUMERIC(18,2) NOT NULL DEFAULT 0,
    liabilities_total NUMERIC(18,2) NOT NULL DEFAULT 0,
    net_worth NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_net_worth_snapshots_workspace_date
ON net_worth_snapshots(workspace_id, snapshot_date DESC);
