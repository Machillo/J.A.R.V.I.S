-- DINCR pre-release database integrity (prepared, NOT applied).
-- HUMAN GATE: review, run the read-only checks, then apply to production.
-- Every statement is idempotent and non-destructive. Orphan cleanup is a
-- separate, commented, manual step.

-- 1. CCSS salary reports must disappear with their workspace (account deletion).
--    Read-only pre-check (expect 0 before VALIDATE succeeds):
--    SELECT COUNT(*) FROM payroll_salary_reports p
--    WHERE NOT EXISTS (SELECT 1 FROM workspaces w WHERE w.id = p.workspace_id);
--    If > 0, those rows belong to already-deleted accounts. Delete them
--    manually after review (destructive, human decision):
--    -- DELETE FROM payroll_salary_reports p
--    -- WHERE NOT EXISTS (SELECT 1 FROM workspaces w WHERE w.id = p.workspace_id);
DO $$
BEGIN
  IF to_regclass('public.payroll_salary_reports') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'payroll_salary_reports_workspace_fkey') THEN
    ALTER TABLE public.payroll_salary_reports
      ADD CONSTRAINT payroll_salary_reports_workspace_fkey
      FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE NOT VALID;
  END IF;
END $$;
-- After the orphan check returns 0:
-- ALTER TABLE public.payroll_salary_reports VALIDATE CONSTRAINT payroll_salary_reports_workspace_fkey;

-- 2. Owner email monitor upserts use ON CONFLICT (workspace_id); guarantee the target.
--    Read-only pre-check (expect no rows):
--    SELECT workspace_id, COUNT(*) FROM email_monitor_settings GROUP BY 1 HAVING COUNT(*) > 1;
DO $$
BEGIN
  IF to_regclass('public.email_monitor_settings') IS NOT NULL THEN
    CREATE UNIQUE INDEX IF NOT EXISTS uq_email_monitor_settings_workspace
      ON public.email_monitor_settings(workspace_id);
  END IF;
END $$;

-- 3. Indexes for the Users Gmail history path and the account-deletion cascade.
DO $$
BEGIN
  IF to_regclass('public.finva_email_messages') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS idx_finva_email_messages_ws_received
      ON public.finva_email_messages(workspace_id, account_id, received_at DESC, id DESC);
    CREATE INDEX IF NOT EXISTS idx_finva_email_messages_account_fk ON public.finva_email_messages(account_id);
  END IF;
  IF to_regclass('public.finva_email_candidates') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS idx_finva_email_candidates_account_fk ON public.finva_email_candidates(account_id);
    CREATE INDEX IF NOT EXISTS idx_finva_email_candidates_transaction_fk
      ON public.finva_email_candidates(transaction_id) WHERE transaction_id IS NOT NULL;
  END IF;
  IF to_regclass('public.finva_gmail_oauth_states') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS idx_finva_gmail_oauth_states_account_fk ON public.finva_gmail_oauth_states(account_id);
  END IF;
  IF to_regclass('public.finva_gmail_connections') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS idx_finva_gmail_connections_legacy_user_fk ON public.finva_gmail_connections(legacy_user_id);
  END IF;
END $$;
