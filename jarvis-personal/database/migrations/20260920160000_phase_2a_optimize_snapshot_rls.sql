-- FINVA Phase 2A: cache the request identity once per statement in snapshot RLS.
-- This preserves the accounts.supabase_user_id -> auth.uid() identity bridge and
-- active workspace membership checks from the original Phase 2A migration.

DROP POLICY IF EXISTS financial_state_snapshots_workspace_read
    ON public.financial_state_snapshots;
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
              SELECT 1
              FROM public.accounts a
              WHERE a.id = wm.account_id
                AND a.supabase_user_id = (SELECT auth.uid())
          )
          AND wm.status = 'active'
    )
);

DROP POLICY IF EXISTS financial_state_snapshots_workspace_insert
    ON public.financial_state_snapshots;
CREATE POLICY financial_state_snapshots_workspace_insert
ON public.financial_state_snapshots
FOR INSERT
TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1
        FROM public.accounts a
        WHERE a.id = financial_state_snapshots.account_id
          AND a.supabase_user_id = (SELECT auth.uid())
    )
    AND EXISTS (
        SELECT 1
        FROM public.workspace_members wm
        WHERE wm.workspace_id = financial_state_snapshots.workspace_id
          AND EXISTS (
              SELECT 1
              FROM public.accounts a
              WHERE a.id = wm.account_id
                AND a.supabase_user_id = (SELECT auth.uid())
          )
          AND wm.status = 'active'
    )
);

DROP POLICY IF EXISTS financial_state_snapshots_workspace_update
    ON public.financial_state_snapshots;
CREATE POLICY financial_state_snapshots_workspace_update
ON public.financial_state_snapshots
FOR UPDATE
TO authenticated
USING (
    EXISTS (
        SELECT 1
        FROM public.accounts a
        WHERE a.id = financial_state_snapshots.account_id
          AND a.supabase_user_id = (SELECT auth.uid())
    )
    AND EXISTS (
        SELECT 1
        FROM public.workspace_members wm
        WHERE wm.workspace_id = financial_state_snapshots.workspace_id
          AND EXISTS (
              SELECT 1
              FROM public.accounts a
              WHERE a.id = wm.account_id
                AND a.supabase_user_id = (SELECT auth.uid())
          )
          AND wm.status = 'active'
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1
        FROM public.accounts a
        WHERE a.id = financial_state_snapshots.account_id
          AND a.supabase_user_id = (SELECT auth.uid())
    )
    AND EXISTS (
        SELECT 1
        FROM public.workspace_members wm
        WHERE wm.workspace_id = financial_state_snapshots.workspace_id
          AND EXISTS (
              SELECT 1
              FROM public.accounts a
              WHERE a.id = wm.account_id
                AND a.supabase_user_id = (SELECT auth.uid())
          )
          AND wm.status = 'active'
    )
);
