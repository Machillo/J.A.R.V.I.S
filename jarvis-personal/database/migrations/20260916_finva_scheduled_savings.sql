BEGIN;

CREATE TABLE IF NOT EXISTS finva_savings_plans (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    monthly_amount NUMERIC(14,2) NOT NULL CHECK (monthly_amount > 0),
    saved_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (saved_amount >= 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL CHECK (end_date >= start_date),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS finva_savings_plan_contributions (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    savings_plan_id BIGINT NOT NULL REFERENCES finva_savings_plans(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    contribution_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finva_savings_plans_workspace ON finva_savings_plans(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_finva_savings_contributions_plan ON finva_savings_plan_contributions(savings_plan_id, contribution_date);

ALTER TABLE finva_savings_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE finva_savings_plan_contributions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE finva_savings_plans, finva_savings_plan_contributions FROM anon, authenticated;
REVOKE ALL ON SEQUENCE finva_savings_plans_id_seq, finva_savings_plan_contributions_id_seq FROM anon, authenticated;

COMMIT;
