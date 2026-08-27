CREATE TABLE IF NOT EXISTS investment_cashflows (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, flow_date DATE NOT NULL DEFAULT CURRENT_DATE,
    flow_type TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
    source TEXT NOT NULL DEFAULT 'manual', description TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_investment_cashflows_user_date ON investment_cashflows(user_id, flow_date);

CREATE TABLE IF NOT EXISTS investment_portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    market_value NUMERIC(14,2) NOT NULL DEFAULT 0, contributed_capital NUMERIC(14,2) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(14,2) NOT NULL DEFAULT 0, unrealized_pnl NUMERIC(14,2) NOT NULL DEFAULT 0,
    dividends NUMERIC(14,2) NOT NULL DEFAULT 0, taxes NUMERIC(14,2) NOT NULL DEFAULT 0,
    commissions NUMERIC(14,2) NOT NULL DEFAULT 0, funding_fees NUMERIC(14,2) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD', source TEXT NOT NULL DEFAULT 'manual', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_investment_snapshots_user_date ON investment_portfolio_snapshots(user_id, snapshot_date);
