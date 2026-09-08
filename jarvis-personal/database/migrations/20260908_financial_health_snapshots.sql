CREATE TABLE IF NOT EXISTS financial_health_snapshots (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    liquidity NUMERIC(14,2) NOT NULL DEFAULT 0,
    recurring_monthly NUMERIC(14,2) NOT NULL DEFAULT 0,
    debt_balance NUMERIC(14,2) NOT NULL DEFAULT 0,
    debt_monthly NUMERIC(14,2) NOT NULL DEFAULT 0,
    salvavidas_coverage NUMERIC(10,4) NOT NULL DEFAULT 0,
    net_worth NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_financial_health_snapshots_workspace_date
ON financial_health_snapshots(workspace_id, snapshot_date DESC);
