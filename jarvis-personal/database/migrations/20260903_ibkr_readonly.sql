ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS snapshot_at TIMESTAMPTZ;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS cash NUMERIC(18,4) NOT NULL DEFAULT 0;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS buying_power NUMERIC(18,4) NOT NULL DEFAULT 0;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS gross_position_value NUMERIC(18,4) NOT NULL DEFAULT 0;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS accrued_cash NUMERIC(18,4) NOT NULL DEFAULT 0;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS account_id_masked TEXT;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS account_mode TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS snapshot_key TEXT;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS sync_method TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS included_in_net_worth BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS exchange_rate_crc NUMERIC(14,6);
ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS market_value_crc NUMERIC(18,2);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ibkr_snapshot_key ON investment_portfolio_snapshots(workspace_id, snapshot_key) WHERE snapshot_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS investment_position_snapshots (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL,
    portfolio_snapshot_id BIGINT NOT NULL REFERENCES investment_portfolio_snapshots(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    sec_type TEXT NOT NULL,
    currency TEXT NOT NULL,
    exchange TEXT,
    position NUMERIC(24,8) NOT NULL DEFAULT 0,
    average_cost NUMERIC(18,6) NOT NULL DEFAULT 0,
    market_price NUMERIC(18,6) NOT NULL DEFAULT 0,
    market_value NUMERIC(18,4) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(18,4) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ibkr_positions_snapshot ON investment_position_snapshots(portfolio_snapshot_id);
