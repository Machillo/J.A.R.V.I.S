-- Phase 4A: auxiliary financial workspace hardening.
-- Non-destructive: legacy user_id stays in place during the migration window.

CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    workspace_id UUID,
    account_name TEXT NOT NULL,
    bank_name TEXT,
    account_last4 TEXT,
    currency TEXT NOT NULL DEFAULT 'CRC',
    current_balance NUMERIC(14,2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE business_projects ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE business_movements ADD COLUMN IF NOT EXISTS workspace_id UUID;

-- Resolve workspace ownership through the canonical account mapping.
UPDATE account_balances ab
SET workspace_id = w.id
FROM accounts a
JOIN workspaces w
  ON w.owner_account_id = a.id
 AND w.workspace_type = 'personal'
WHERE ab.workspace_id IS NULL
  AND a.legacy_allowed_user_id = ab.user_id;

UPDATE business_projects bp
SET workspace_id = w.id
FROM accounts a
JOIN workspaces w
  ON w.owner_account_id = a.id
 AND w.workspace_type = 'personal'
WHERE bp.workspace_id IS NULL
  AND a.legacy_allowed_user_id = bp.user_id;

UPDATE business_movements bm
SET workspace_id = COALESCE(
    bp.workspace_id,
    (
        SELECT w.id
        FROM accounts a
        JOIN workspaces w
          ON w.owner_account_id = a.id
         AND w.workspace_type = 'personal'
        WHERE a.legacy_allowed_user_id = bm.user_id
        ORDER BY w.created_at, w.id
        LIMIT 1
    )
)
FROM business_projects bp
WHERE bm.workspace_id IS NULL
  AND bp.id = bm.business_id;

CREATE INDEX IF NOT EXISTS idx_account_balances_workspace_active
ON account_balances(workspace_id, is_active);

CREATE INDEX IF NOT EXISTS idx_business_projects_workspace
ON business_projects(workspace_id, status, name);

CREATE INDEX IF NOT EXISTS idx_business_movements_workspace_date
ON business_movements(workspace_id, movement_date DESC, id DESC);

-- Add FKs only when not already present.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'account_balances_workspace_id_fkey'
    ) THEN
        ALTER TABLE account_balances
        ADD CONSTRAINT account_balances_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'business_projects_workspace_id_fkey'
    ) THEN
        ALTER TABLE business_projects
        ADD CONSTRAINT business_projects_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'business_movements_workspace_id_fkey'
    ) THEN
        ALTER TABLE business_movements
        ADD CONSTRAINT business_movements_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE NOT VALID;
    END IF;
END $$;

-- Audit result. All three unmapped counts should be zero before later NOT NULL hardening.
SELECT
    (SELECT COUNT(*) FROM account_balances WHERE workspace_id IS NULL) AS account_balances_unmapped,
    (SELECT COUNT(*) FROM business_projects WHERE workspace_id IS NULL) AS business_projects_unmapped,
    (SELECT COUNT(*) FROM business_movements WHERE workspace_id IS NULL) AS business_movements_unmapped;
