-- DINCR financial ownership: forensic evidence queries (READ-ONLY).
--
-- Run ONE query at a time ("Run selected" in the Supabase SQL editor): the
-- editor only shows the last result set. Replace the placeholders:
--   <WORKSPACE_ID>  a workspaces.id under review
--   <ACCOUNT_ID>    the accounts.id that owns it
-- Every query returns identifiers, timestamps and counts only; none returns
-- names, emails, descriptions or amounts, except E7 (aggregated debt totals of
-- one workspace, needed to prove whether debts existed). Keep the output out of
-- tickets, logs and the repository.

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

-- E5. API trace of debt writes by one account (idempotency records are never
--     purged). response_body is reduced to the debt id: no names or amounts.
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
