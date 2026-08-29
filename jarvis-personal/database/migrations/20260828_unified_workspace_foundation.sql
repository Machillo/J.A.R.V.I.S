-- JARVIS unified identity/workspace foundation
-- Phase 1: non-destructive. Existing Personal tables and user_id columns remain untouched.
-- Safe to re-run.
-- NOTE: This version intentionally does not depend on the legacy `users` table shape.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legacy_allowed_user_id BIGINT UNIQUE REFERENCES allowed_users(id) ON DELETE SET NULL,
    supabase_user_id UUID UNIQUE,
    primary_email TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin', 'owner')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'blocked', 'pending')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_primary_email_ci
ON accounts (LOWER(primary_email));

CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_key TEXT NOT NULL UNIQUE,
    owner_account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    workspace_type TEXT NOT NULL DEFAULT 'personal' CHECK (workspace_type IN ('personal', 'business')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_account
ON workspaces(owner_account_id);

CREATE TABLE IF NOT EXISTS workspace_members (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    member_role TEXT NOT NULL DEFAULT 'member' CHECK (member_role IN ('owner', 'admin', 'member', 'viewer')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'invited', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_account
ON workspace_members(account_id, status);

-- Backfill one permanent JARVIS account for each existing Personal allowed_user.
-- Phase 1 deliberately uses only allowed_users, whose live schema is already authoritative.
-- display_name remains NULL for now and can be enriched later without affecting identity.
-- Invalid/empty legacy Supabase IDs are preserved only in allowed_users; they are not cast into UUID.
INSERT INTO accounts (
    legacy_allowed_user_id,
    supabase_user_id,
    primary_email,
    display_name,
    role,
    status,
    created_at,
    last_login_at
)
SELECT
    au.id,
    CASE
        WHEN COALESCE(au.supabase_user_id, '') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        THEN au.supabase_user_id::UUID
        ELSE NULL
    END,
    LOWER(TRIM(au.email)),
    NULL,
    CASE
        WHEN au.role = 'owner' THEN 'owner'
        WHEN au.role = 'admin' THEN 'admin'
        ELSE 'user'
    END,
    CASE
        WHEN au.status IN ('active', 'blocked', 'pending') THEN au.status
        WHEN au.status = 'approved' THEN 'active'
        ELSE 'pending'
    END,
    au.created_at,
    au.last_login_at
FROM allowed_users au
ON CONFLICT (legacy_allowed_user_id) DO UPDATE SET
    supabase_user_id = COALESCE(EXCLUDED.supabase_user_id, accounts.supabase_user_id),
    primary_email = EXCLUDED.primary_email,
    role = EXCLUDED.role,
    status = EXCLUDED.status,
    last_login_at = COALESCE(EXCLUDED.last_login_at, accounts.last_login_at),
    updated_at = NOW();

-- Every migrated account receives a Personal workspace. Business workspaces will be migrated later.
INSERT INTO workspaces (
    workspace_key,
    owner_account_id,
    name,
    workspace_type,
    status
)
SELECT
    'personal:' || a.id::TEXT,
    a.id,
    COALESCE(NULLIF(a.display_name, ''), SPLIT_PART(a.primary_email, '@', 1)) || ' Personal',
    'personal',
    'active'
FROM accounts a
WHERE a.legacy_allowed_user_id IS NOT NULL
ON CONFLICT (workspace_key) DO UPDATE SET
    owner_account_id = EXCLUDED.owner_account_id,
    name = EXCLUDED.name,
    updated_at = NOW();

INSERT INTO workspace_members (workspace_id, account_id, member_role, status)
SELECT w.id, w.owner_account_id, 'owner', 'active'
FROM workspaces w
WHERE w.workspace_type = 'personal'
ON CONFLICT (workspace_id, account_id) DO UPDATE SET
    member_role = 'owner',
    status = 'active',
    updated_at = NOW();

-- Validation view for this migration only. It exposes no financial rows.
CREATE OR REPLACE VIEW v_account_workspace_migration_status AS
SELECT
    au.id AS legacy_allowed_user_id,
    au.email AS legacy_email,
    a.id AS account_id,
    a.supabase_user_id,
    a.role AS account_role,
    w.id AS personal_workspace_id,
    w.name AS personal_workspace_name,
    wm.member_role,
    (a.id IS NOT NULL AND w.id IS NOT NULL AND wm.id IS NOT NULL) AS foundation_ready
FROM allowed_users au
LEFT JOIN accounts a ON a.legacy_allowed_user_id = au.id
LEFT JOIN workspaces w
    ON w.owner_account_id = a.id
   AND w.workspace_type = 'personal'
   AND w.workspace_key = 'personal:' || a.id::TEXT
LEFT JOIN workspace_members wm
    ON wm.workspace_id = w.id
   AND wm.account_id = a.id;
