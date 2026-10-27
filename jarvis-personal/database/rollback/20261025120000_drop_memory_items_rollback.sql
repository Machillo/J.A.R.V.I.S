-- MANUAL rollback of 20261025120000_drop_memory_items.sql.
-- Human decision only; never run automatically.
--
-- What it does: recreates memory_items empty, with the same columns, indexes and dincr_app grant
-- it had (20260926125000 / 20260926150000). The dropped notes are not restored: only a backup
-- taken before the drop has them. Useful only if code that uses the table is rolled back too.
--
-- How to run it: BACKUP_VERIFIED gate open; a second person reads this file; psql -v
-- ON_ERROR_STOP=1 as postgres, one transaction. Idempotent (IF NOT EXISTS).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

CREATE TABLE IF NOT EXISTS public.memory_items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    category TEXT NOT NULL DEFAULT 'other',
    title TEXT,
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,
    source TEXT NOT NULL DEFAULT 'manual',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_memory_items_user_active ON public.memory_items(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_memory_items_category ON public.memory_items(category);
CREATE INDEX IF NOT EXISTS idx_memory_items_workspace_active ON public.memory_items(workspace_id, is_active);
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.memory_items TO dincr_app;
GRANT USAGE ON SEQUENCE public.memory_items_id_seq TO dincr_app;

COMMIT;
