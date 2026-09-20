-- FINVA Phase 2A: longitudinal financial state snapshots.
-- Isolated from Phase 1 ingestion/email tables.

CREATE TABLE IF NOT EXISTS public.financial_state_snapshots (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    period TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'financial-state-v1',
    state JSONB NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_financial_state_snapshots_workspace_date
    ON public.financial_state_snapshots(workspace_id, snapshot_date DESC);

ALTER TABLE public.financial_state_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS financial_state_snapshots_workspace_read ON public.financial_state_snapshots;
CREATE POLICY financial_state_snapshots_workspace_read
ON public.financial_state_snapshots
FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1
        FROM public.workspace_members wm
        WHERE wm.workspace_id = financial_state_snapshots.workspace_id
          AND EXISTS (
              SELECT 1 FROM public.accounts a
              WHERE a.id = wm.account_id
                AND a.supabase_user_id = auth.uid()
          )
          AND wm.status = 'active'
    )
);

DROP POLICY IF EXISTS financial_state_snapshots_workspace_insert ON public.financial_state_snapshots;
CREATE POLICY financial_state_snapshots_workspace_insert
ON public.financial_state_snapshots
FOR INSERT
TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.accounts a
        WHERE a.id = financial_state_snapshots.account_id
          AND a.supabase_user_id = auth.uid()
    )
    AND EXISTS (
        SELECT 1
        FROM public.workspace_members wm
        WHERE wm.workspace_id = financial_state_snapshots.workspace_id
          AND EXISTS (
              SELECT 1 FROM public.accounts a
              WHERE a.id = wm.account_id
                AND a.supabase_user_id = auth.uid()
          )
          AND wm.status = 'active'
    )
);

DROP POLICY IF EXISTS financial_state_snapshots_workspace_update ON public.financial_state_snapshots;
CREATE POLICY financial_state_snapshots_workspace_update
ON public.financial_state_snapshots
FOR UPDATE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.accounts a
        WHERE a.id = financial_state_snapshots.account_id
          AND a.supabase_user_id = auth.uid()
    )
    AND EXISTS (
        SELECT 1
        FROM public.workspace_members wm
        WHERE wm.workspace_id = financial_state_snapshots.workspace_id
          AND EXISTS (
              SELECT 1 FROM public.accounts a
              WHERE a.id = wm.account_id
                AND a.supabase_user_id = auth.uid()
          )
          AND wm.status = 'active'
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.accounts a
        WHERE a.id = financial_state_snapshots.account_id
          AND a.supabase_user_id = auth.uid()
    )
    AND EXISTS (
        SELECT 1
        FROM public.workspace_members wm
        WHERE wm.workspace_id = financial_state_snapshots.workspace_id
          AND EXISTS (
              SELECT 1 FROM public.accounts a
              WHERE a.id = wm.account_id
                AND a.supabase_user_id = auth.uid()
          )
          AND wm.status = 'active'
    )
);
