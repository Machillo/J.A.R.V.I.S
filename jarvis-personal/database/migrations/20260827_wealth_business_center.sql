CREATE TABLE IF NOT EXISTS business_projects (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, name TEXT NOT NULL,
    description TEXT, ownership_pct NUMERIC(6,2) NOT NULL DEFAULT 100,
    status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_business_projects_user ON business_projects(user_id);
CREATE TABLE IF NOT EXISTS business_movements (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
    business_id BIGINT NOT NULL REFERENCES business_projects(id) ON DELETE CASCADE,
    movement_date DATE NOT NULL DEFAULT CURRENT_DATE, movement_type TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL, description TEXT NOT NULL, category TEXT,
    transaction_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_business_movements_user_date ON business_movements(user_id,movement_date);
