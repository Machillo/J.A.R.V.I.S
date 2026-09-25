-- DINCR financial ownership: forensic evidence queries (READ-ONLY).
--
-- Run ONE query at a time ("Run selected" in the Supabase SQL editor): the
-- editor only shows the last result set. Replace the placeholders:
--   <WORKSPACE_ID>  a workspaces.id under review
--   <ACCOUNT_ID>    the accounts.id that owns it
-- Queries return identifiers, timestamps and counts, never names, emails or
-- descriptions. Two return amounts of ONE workspace because the question needs
-- them: E7 (aggregated debt totals) and E17 (declared profile figures behind a
-- Home number). Keep every output out of tickets, logs and the repository.

-- E1. Which identity does each debt's legacy user_id denote, per id space?
--     account_by_users_space = owner_account_id means the row was written by the
--     DINCR users.id bridge for the workspace owner: consistent, not a mismatch.
SELECT d.id,
       d.workspace_id,
       w.owner_account_id,
       d.user_id,
       (SELECT a.id FROM public.accounts a WHERE a.legacy_allowed_user_id = d.user_id) AS account_by_allowed_users_space,
       (SELECT a.id FROM public.users u
          JOIN public.accounts a ON lower(a.primary_email) = lower(u.email)
         WHERE u.id = d.user_id) AS account_by_users_space,
       d.created_at,
       d.updated_at
FROM public.debts d
LEFT JOIN public.workspaces w ON w.id = d.workspace_id
ORDER BY d.id;

-- E2. The users.id bridge of every account (the id DINCR writes into user_id).
SELECT a.id AS account_id,
       a.legacy_allowed_user_id,
       (SELECT u.id FROM public.users u WHERE lower(u.email) = lower(a.primary_email)) AS users_id,
       a.created_at AS account_created_at,
       (SELECT au.created_at FROM public.allowed_users au WHERE au.id = a.legacy_allowed_user_id) AS allowed_user_created_at,
       (SELECT u.created_at FROM public.users u WHERE lower(u.email) = lower(a.primary_email)) AS users_created_at,
       (SELECT w.id FROM public.workspaces w WHERE w.owner_account_id = a.id AND w.workspace_type = 'personal') AS personal_workspace_id,
       (SELECT w.created_at FROM public.workspaces w WHERE w.owner_account_id = a.id AND w.workspace_type = 'personal') AS workspace_created_at
FROM public.accounts a
ORDER BY a.legacy_allowed_user_id;

-- E3. Bulk-insert signature: several rows of one workspace sharing the exact
--     same created_at. The app opens one transaction per create request, so
--     identical NOW() values point at one SQL statement/script, not the app.
SELECT 'debts' AS table_name, workspace_id, created_at, COUNT(*) AS rows_in_same_instant, array_agg(id ORDER BY id) AS ids
FROM public.debts GROUP BY workspace_id, created_at HAVING COUNT(*) > 1
UNION ALL
SELECT 'financial_goals', workspace_id, created_at, COUNT(*), array_agg(id ORDER BY id)
FROM public.financial_goals GROUP BY workspace_id, created_at HAVING COUNT(*) > 1
UNION ALL
SELECT 'expenses', workspace_id, created_at, COUNT(*), array_agg(id ORDER BY id)
FROM public.expenses GROUP BY workspace_id, created_at HAVING COUNT(*) > 1
UNION ALL
SELECT 'salaries', workspace_id, created_at, COUNT(*), array_agg(id ORDER BY id)
FROM public.salaries GROUP BY workspace_id, created_at HAVING COUNT(*) > 1
ORDER BY 1, 3;

-- E4. Debt ids that no longer exist (deleted rows or rolled-back inserts).
SELECT g.id AS missing_debt_id
FROM generate_series(1, (SELECT last_value FROM public.debts_id_seq)) AS g(id)
WHERE NOT EXISTS (SELECT 1 FROM public.debts d WHERE d.id = g.id)
ORDER BY 1;

-- E5. API trace of debt writes by one account (the app does not purge
--     idempotency records after expires_at; they cascade with the account).
--     response_body is reduced to the debt id: no names or amounts.
--     A debt created through the app leaves a POST here; rows that exist with no
--     matching POST were not created through the app's debt endpoint.
SELECT created_at, method, path, status, response_status,
       response_body ->> 'id' AS debt_id
FROM public.operation_idempotency
WHERE account_id = '<ACCOUNT_ID>'::uuid
  AND path LIKE '/user-product/finance/debts%'
ORDER BY created_at;

-- E6. Payments of debts that no longer exist: pay_user_debt writes a
--     transaction whose notes are 'debt_id:<id>'; transactions do not cascade
--     from debts, so they survive a debt deletion.
SELECT t.id AS transaction_id, t.workspace_id, t.created_at, t.notes AS debt_ref,
       EXISTS (SELECT 1 FROM public.debts d
               WHERE t.notes = 'debt_id:' || d.id::TEXT) AS debt_still_exists
FROM public.transactions t
WHERE t.workspace_id = '<WORKSPACE_ID>'::uuid
  AND t.source = 'finva_debt_payment'
ORDER BY t.created_at;

-- E7. Daily financial state snapshots of one workspace: shows whether debts
--     existed and when the total dropped (aggregates only, no rows).
SELECT snapshot_date, captured_at,
       state -> 'debt' ->> 'active_count' AS active_debt_count,
       state -> 'debt' ->> 'total' AS debt_total
FROM public.financial_state_snapshots
WHERE workspace_id = '<WORKSPACE_ID>'::uuid
ORDER BY snapshot_date;

-- E8. What else survives in one workspace (a wipe of everything points at an
--     account/workspace deletion; debts alone at a debt deletion).
SELECT 'debts' AS table_name, COUNT(*) FROM public.debts WHERE workspace_id = '<WORKSPACE_ID>'::uuid
UNION ALL SELECT 'debt_payments', COUNT(*) FROM public.debt_payments WHERE workspace_id = '<WORKSPACE_ID>'::uuid
UNION ALL SELECT 'transactions', COUNT(*) FROM public.transactions WHERE workspace_id = '<WORKSPACE_ID>'::uuid
UNION ALL SELECT 'expenses', COUNT(*) FROM public.expenses WHERE workspace_id = '<WORKSPACE_ID>'::uuid
UNION ALL SELECT 'salaries', COUNT(*) FROM public.salaries WHERE workspace_id = '<WORKSPACE_ID>'::uuid
UNION ALL SELECT 'financial_goals', COUNT(*) FROM public.financial_goals WHERE workspace_id = '<WORKSPACE_ID>'::uuid
UNION ALL SELECT 'financial_state_snapshots', COUNT(*) FROM public.financial_state_snapshots WHERE workspace_id = '<WORKSPACE_ID>'::uuid
UNION ALL SELECT 'operation_idempotency', COUNT(*) FROM public.operation_idempotency WHERE account_id = '<ACCOUNT_ID>'::uuid;

-- E9. Deleted identities: gaps in allowed_users / users ids (deleted accounts).
SELECT 'allowed_users' AS id_space, g.id
FROM generate_series(1, (SELECT MAX(id) FROM public.allowed_users)) AS g(id)
WHERE NOT EXISTS (SELECT 1 FROM public.allowed_users au WHERE au.id = g.id)
UNION ALL
SELECT 'users', g.id
FROM generate_series(1, (SELECT MAX(id) FROM public.users)) AS g(id)
WHERE NOT EXISTS (SELECT 1 FROM public.users u WHERE u.id = g.id)
ORDER BY 1, 2;

-- ===========================================================================
-- Round 2 (forensics of a workspace whose debts disappeared). Same rules: run
-- one query at a time; <ALLOWED_ID> / <USERS_ID> are that person's
-- allowed_users.id and users.id from E2.
-- ===========================================================================

-- E10. Every FK that can delete financial rows, with its ON DELETE rule.
--      Confirms/refutes: (a) debts.user_id -> users/allowed_users cascades;
--      (b) the cross-id-space risk: a user_id written in one space whose FK
--      points at the other space is deleted when an UNRELATED person is deleted.
SELECT child.relname AS child_table, att.attname AS child_column,
       parent.relname AS parent_table, c.conname,
       CASE c.confdeltype WHEN 'c' THEN 'CASCADE' WHEN 'n' THEN 'SET NULL' WHEN 'r' THEN 'RESTRICT'
                          WHEN 'd' THEN 'SET DEFAULT' ELSE 'NO ACTION' END AS on_delete,
       c.convalidated
FROM pg_constraint c
JOIN pg_class child ON child.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = child.relnamespace AND ns.nspname = 'public'
JOIN pg_class parent ON parent.oid = c.confrelid
JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
WHERE c.contype = 'f'
  AND (parent.relname IN ('users', 'allowed_users', 'accounts', 'workspaces', 'debts')
       OR child.relname IN ('debts', 'debt_payments', 'transactions'))
ORDER BY parent.relname, child.relname, att.attname;

-- E11. Cumulative row counters since the last statistics reset: how many debt
--      rows were ever inserted/deleted. Confirms deletions happened and bounds
--      how many (includes the Owner's test deletions and isolation sentinels).
SELECT s.relname, s.n_tup_ins, s.n_tup_upd, s.n_tup_del, s.n_live_tup,
       (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()) AS stats_since
FROM pg_stat_user_tables s
WHERE s.relname IN ('debts', 'debt_payments', 'transactions', 'accounts', 'workspaces', 'allowed_users', 'users')
ORDER BY s.relname;

-- E12. Identity timeline of one account (no emails). If the account or the
--      workspace was created AFTER the debts were entered, the old workspace
--      (and its debts) was removed by the workspace cascade; if both predate
--      them, the rows were deleted individually or never stored here.
SELECT a.created_at AS account_created_at, a.updated_at AS account_updated_at,
       a.last_login_at AS account_last_login_at, a.status AS account_status,
       au.created_at AS allowed_user_created_at, au.last_login_at AS allowed_user_last_login_at,
       au.status AS allowed_user_status,
       w.created_at AS workspace_created_at, w.updated_at AS workspace_updated_at,
       (SELECT u.created_at FROM public.users u WHERE lower(u.email) = lower(a.primary_email)) AS users_row_created_at
FROM public.accounts a
LEFT JOIN public.allowed_users au ON au.id = a.legacy_allowed_user_id
LEFT JOIN public.workspaces w ON w.owner_account_id = a.id AND w.workspace_type = 'personal'
WHERE a.id = '<ACCOUNT_ID>'::uuid;

-- E13. Server-side screen trail of one account (product_events, kept since
--      2026-09-10, never purged). Shows the plan over time, whether the Debts
--      screen was opened and on which days, and whether every event carries the
--      same workspace_id (a second workspace_id = the workspace was replaced).
SELECT date_trunc('day', created_at)::date AS day, workspace_id, plan_code,
       COUNT(*) AS events,
       COUNT(*) FILTER (WHERE event_name = 'debts_opened') AS debts_opened,
       MIN(created_at) AS first_event, MAX(created_at) AS last_event
FROM public.product_events
WHERE account_id = '<ACCOUNT_ID>'::uuid OR workspace_id = '<WORKSPACE_ID>'::uuid
GROUP BY 1, 2, 3
ORDER BY 1;

-- E14. Screen trails of accounts that no longer exist (account_id was set to
--      NULL by the account deletion) or of workspaces that no longer exist.
--      Confirms/refutes: the debts were entered under ANOTHER login that was
--      later deleted (compare the dates with E13).
SELECT workspace_id, plan_code, MIN(created_at) AS first_event, MAX(created_at) AS last_event,
       COUNT(*) AS events, COUNT(*) FILTER (WHERE event_name = 'debts_opened') AS debts_opened
FROM public.product_events pe
WHERE pe.account_id IS NULL
   OR NOT EXISTS (SELECT 1 FROM public.workspaces w WHERE w.id = pe.workspace_id)
GROUP BY workspace_id, plan_code
ORDER BY first_event;

-- E15. Automatic incident reports of one account (screen, time, reference; no
--      message text). Confirms/refutes: creating the debts failed and they were
--      never stored. Automatic reports exist only since 2026-09-20 (Phase 0A):
--      an empty result says nothing about earlier failures.
SELECT created_at, last_seen_at, source, severity, category, screen, platform,
       app_version, occurrence_count, error_reference, status
FROM public.feedback_reports
WHERE account_id = '<ACCOUNT_ID>'::uuid
ORDER BY created_at;

-- E16. Rows carrying this person's legacy ids OUTSIDE their workspace.
--      Confirms/refutes: their rows were written into another workspace.
--      Check E2 first: a value that is also another account's id in the other
--      space is ambiguous by itself.
SELECT 'debts' AS table_name, workspace_id, user_id, COUNT(*) FROM public.debts
 WHERE user_id IN (<ALLOWED_ID>, <USERS_ID>) AND workspace_id IS DISTINCT FROM '<WORKSPACE_ID>'::uuid GROUP BY 1, 2, 3
UNION ALL
SELECT 'transactions', workspace_id, user_id, COUNT(*) FROM public.transactions
 WHERE user_id IN (<ALLOWED_ID>, <USERS_ID>) AND workspace_id IS DISTINCT FROM '<WORKSPACE_ID>'::uuid GROUP BY 1, 2, 3
UNION ALL
SELECT 'expenses', workspace_id, user_id, COUNT(*) FROM public.expenses
 WHERE user_id IN (<ALLOWED_ID>, <USERS_ID>) AND workspace_id IS DISTINCT FROM '<WORKSPACE_ID>'::uuid GROUP BY 1, 2, 3
UNION ALL
SELECT 'financial_goals', workspace_id, user_id, COUNT(*) FROM public.financial_goals
 WHERE user_id IN (<ALLOWED_ID>, <USERS_ID>) AND workspace_id IS DISTINCT FROM '<WORKSPACE_ID>'::uuid GROUP BY 1, 2, 3
UNION ALL
SELECT 'payroll_events', workspace_id, user_id, COUNT(*) FROM public.payroll_events
 WHERE user_id IN (<ALLOWED_ID>, <USERS_ID>) AND workspace_id IS DISTINCT FROM '<WORKSPACE_ID>'::uuid GROUP BY 1, 2, 3;

-- E17. Where a Home figure comes from when the ledger is empty. Every plan's
--      hero is computed from the DECLARED profile plus recurring items and
--      account balances, not from transactions (see the PR description).
--      Returns the inputs of one workspace; keep the output private.
--      finva_recurring_items is not queried: in production it does not exist
--      (Basic/VIP reads create it inside a transaction that is never committed),
--      so recurring items are always empty there.
SELECT
    (SELECT p.code FROM public.account_subscriptions s JOIN public.plans p ON p.id = s.plan_id
      WHERE s.account_id = '<ACCOUNT_ID>'::uuid) AS plan,
    fp.income_type, fp.fixed_monthly_salary, fp.hourly_rate, fp.hours_per_day, fp.work_days_per_week,
    fp.essential_monthly_expenses, fp.liquid_savings, fp.emergency_fund_target,
    fp.created_at AS profile_created_at, fp.updated_at AS profile_updated_at,
    (SELECT COUNT(*) FROM public.account_balances b WHERE b.workspace_id = '<WORKSPACE_ID>'::uuid) AS account_balance_rows,
    (SELECT COUNT(*) FROM public.payroll_events pe WHERE pe.workspace_id = '<WORKSPACE_ID>'::uuid) AS payroll_events_rows,
    (SELECT COUNT(*) FROM public.finva_savings_plans sp WHERE sp.workspace_id = '<WORKSPACE_ID>'::uuid) AS savings_plans_rows
FROM public.financial_profiles fp
WHERE fp.account_id = '<ACCOUNT_ID>'::uuid;

-- ===========================================================================
-- Round 3. product_events has no `screen` column: the screen is `surface`
-- (plus event_name). Replace <AUTH_USER_ID> with accounts.supabase_user_id.
-- ===========================================================================

-- E18. Which code created each users (legacy finance) row, from its defaults:
--      country 'Unknown' / timezone 'UTC' = user_product._legacy_financial_user_id
--      (first Income/Expense/Debt/Goal/Transaction write); 'Costa Rica' /
--      'America/Costa_Rica' = the mail connection bridge. No emails or names.
SELECT u.id, u.created_at, u.country, u.timezone,
       (SELECT a.id FROM public.accounts a WHERE lower(trim(a.primary_email)) = lower(trim(u.email))) AS account_id
FROM public.users u
ORDER BY u.id;

-- E19. The account balances that feed a Home figure (they replace the declared
--      savings only when CRC and counted in net worth). Balance shown only then.
SELECT b.id, b.created_at, b.source, b.currency, b.include_in_net_worth, b.is_active,
       CASE WHEN b.include_in_net_worth AND b.currency = 'CRC' THEN b.current_balance END AS counted_balance
FROM public.account_balances b
WHERE b.workspace_id = '<WORKSPACE_ID>'::uuid
ORDER BY b.id;

-- E20. Every financial row created in a time window, in ANY workspace (ids and
--      workspaces only). Confirms/refutes: a row written at the moment the users
--      bridge row was created (E18) still exists somewhere.
SELECT 'debts' AS table_name, id, workspace_id, user_id, created_at FROM public.debts
 WHERE created_at BETWEEN '<FROM_UTC>'::timestamptz AND '<TO_UTC>'::timestamptz
UNION ALL SELECT 'expenses', id, workspace_id, user_id, created_at FROM public.expenses
 WHERE created_at BETWEEN '<FROM_UTC>'::timestamptz AND '<TO_UTC>'::timestamptz
UNION ALL SELECT 'salaries', id, workspace_id, user_id, created_at FROM public.salaries
 WHERE created_at BETWEEN '<FROM_UTC>'::timestamptz AND '<TO_UTC>'::timestamptz
UNION ALL SELECT 'financial_goals', id, workspace_id, user_id, created_at FROM public.financial_goals
 WHERE created_at BETWEEN '<FROM_UTC>'::timestamptz AND '<TO_UTC>'::timestamptz
UNION ALL SELECT 'transactions', id, workspace_id, user_id, created_at FROM public.transactions
 WHERE created_at BETWEEN '<FROM_UTC>'::timestamptz AND '<TO_UTC>'::timestamptz
ORDER BY created_at;

-- E21. The screen trail of one account in a window, event by event (surface,
--      not screen). Shows what was open around a given instant.
SELECT created_at, event_name, surface, success, plan_code, app_version
FROM public.product_events
WHERE account_id = '<ACCOUNT_ID>'::uuid
  AND created_at BETWEEN '<FROM_UTC>'::timestamptz AND '<TO_UTC>'::timestamptz
ORDER BY created_at;

-- E22. Supabase Auth audit trail of one Auth user (logins, refreshes, logouts),
--      if the project writes auth audit logs to the database. Shows whether the
--      account was used on the days rows could have been deleted.
SELECT created_at, payload ->> 'action' AS action
FROM auth.audit_log_entries
WHERE payload ->> 'actor_id' = '<AUTH_USER_ID>'
   OR payload -> 'traits' ->> 'user_id' = '<AUTH_USER_ID>'
ORDER BY created_at;

-- E23. Normalized statements ever executed against debts since the statistics
--      reset (pg_stat_statements strips literal values). App deletes look like
--      "DELETE FROM debts WHERE id=$1 AND workspace_id=$2 RETURNING id"; any
--      other DELETE/UPDATE/INSERT shape on debts is a manual or script write
--      (e.g. the single-statement insert behind rows sharing one created_at).
SELECT s.calls, s.rows, left(regexp_replace(s.query, '\s+', ' ', 'g'), 300) AS normalized_query,
       (SELECT stats_reset FROM pg_stat_statements_info) AS stats_since
FROM pg_stat_statements s
WHERE s.query ~* '\m(delete|update|insert)\M' AND s.query ~* '\mdebts\M'
ORDER BY s.calls DESC;
