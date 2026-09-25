-- DINCR financial ownership PREFLIGHT / POSTFLIGHT (read-only).
--
-- Run the whole file in the Supabase SQL editor (or psql) before AND after the
-- migration 20260925120000_financial_ownership_integrity.sql. It creates the
-- audit functions only in pg_temp (session-local, never persisted), switches the
-- transaction to READ ONLY and returns ONE result set with identifiers only:
-- no names, emails, amounts or descriptions. Nothing is committed; temp
-- functions disappear with the session. Run ROLLBACK afterwards if your client
-- keeps the session open.
--
-- The function block below is a verbatim copy of the migration's block with
-- public.dincr_ -> pg_temp.dincr_ (guarded by backend/tests/test_financial_ownership_integrity.py).
--
-- Result sections:
--   summary   one line per (table, classification, issue) with a row count
--   row       every non-OK row: ids, workspace, parent workspace, legacy user_id and
--             the accounts that user_id can denote in either legacy id space
--   identity  identity-core checks (accounts / workspaces / legacy bridges)
--   user_id_only_table  public tables that still carry user_id without workspace_id
--   unguarded_table  tables with user_id AND workspace_id outside the guarded list
--   user_id_fk  which table each financial user_id column really references
--              (allowed_users vs users) and its ON DELETE rule

BEGIN;

-- BEGIN DINCR OWNERSHIP AUDIT FUNCTIONS
CREATE OR REPLACE FUNCTION pg_temp.dincr_ownership_tables()
RETURNS TABLE (table_name TEXT, parent_table TEXT, parent_column TEXT)
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT t.table_name, t.parent_table, t.parent_column
    FROM (VALUES
        ('events', NULL, NULL),
        ('salaries', NULL, NULL),
        ('bonuses', NULL, NULL),
        ('debts', NULL, NULL),
        ('debt_payments', 'debts', 'debt_id'),
        ('savings', NULL, NULL),
        ('investments', NULL, NULL),
        ('expenses', NULL, NULL),
        ('employment_profile', NULL, NULL),
        ('payroll_deductions', NULL, NULL),
        ('payroll_events', NULL, NULL),
        ('financial_goals', NULL, NULL),
        ('payment_schedules', NULL, NULL),
        ('pay_schedule', NULL, NULL),
        ('credit_card_settings', NULL, NULL),
        ('transactions', NULL, NULL),
        ('exchange_rates', NULL, NULL),
        ('receivables', NULL, NULL),
        ('receivable_payments', 'receivables', 'receivable_id'),
        ('receivable_entries', 'receivables', 'receivable_id'),
        ('fixed_expenses', NULL, NULL),
        ('fixed_expense_matches', 'fixed_expenses', 'fixed_expense_id'),
        ('investment_cashflows', NULL, NULL),
        ('investment_portfolio_snapshots', NULL, NULL),
        ('business_projects', NULL, NULL),
        ('business_movements', 'business_projects', 'business_id'),
        -- Financial tables created after Phase 2A with the same dual legacy user_id.
        ('account_balances', NULL, NULL),
        ('account_balance_history', 'account_balances', 'financial_account_id'),
        ('net_worth_snapshots', NULL, NULL),
        ('payroll_salary_reports', NULL, NULL)
    ) AS t(table_name, parent_table, parent_column)
$fn$;

-- The id space a table's legacy user_id really points at: the table its FK
-- references ('users' or 'allowed_users'), or NULL when there is no such FK (or
-- more than one), in which case both spaces are accepted during the transition.
CREATE OR REPLACE FUNCTION pg_temp.dincr_user_id_space(p_table TEXT)
RETURNS TEXT
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT CASE WHEN COUNT(DISTINCT parent.relname) = 1 THEN MIN(parent.relname::TEXT) END
    FROM pg_catalog.pg_constraint c
    JOIN pg_catalog.pg_class child ON child.oid = c.conrelid
    JOIN pg_catalog.pg_namespace ns ON ns.oid = child.relnamespace AND ns.nspname = 'public'
    JOIN pg_catalog.pg_class parent ON parent.oid = c.confrelid
    JOIN pg_catalog.pg_namespace pns ON pns.oid = parent.relnamespace AND pns.nspname = 'public'
    JOIN pg_catalog.pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND cardinality(c.conkey) = 1 AND att.attname = 'user_id'
      AND child.relname = p_table
      AND parent.relname IN ('users', 'allowed_users')
$fn$;

-- True when p_user_id is an identity of an account that owns or is an active
-- member of p_workspace_id, in p_space ('users', 'allowed_users') or, when
-- p_space is NULL, in either legacy id space.
CREATE OR REPLACE FUNCTION pg_temp.dincr_legacy_id_belongs_to_workspace(p_user_id BIGINT, p_workspace_id UUID, p_space TEXT DEFAULT NULL)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT p_user_id IS NOT NULL AND p_workspace_id IS NOT NULL AND EXISTS (
        SELECT 1
        FROM (
            SELECT w.owner_account_id AS account_id
            FROM public.workspaces w
            WHERE w.id = p_workspace_id
            UNION
            SELECT wm.account_id
            FROM public.workspace_members wm
            WHERE wm.workspace_id = p_workspace_id
              AND wm.status = 'active'
        ) m
        JOIN public.accounts a ON a.id = m.account_id
        WHERE (p_space IS DISTINCT FROM 'users' AND a.legacy_allowed_user_id = p_user_id)
           OR (p_space IS DISTINCT FROM 'allowed_users' AND EXISTS (
                SELECT 1
                FROM public.users u
                WHERE u.id = p_user_id
                  AND lower(trim(u.email)) = lower(trim(a.primary_email))
           ))
    )
$fn$;

-- Every account that p_user_id can denote, in p_space or (NULL) either space.
CREATE OR REPLACE FUNCTION pg_temp.dincr_legacy_id_accounts(p_user_id BIGINT, p_space TEXT DEFAULT NULL)
RETURNS UUID[]
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT COALESCE(array_agg(DISTINCT a.id ORDER BY a.id), ARRAY[]::UUID[])
    FROM public.accounts a
    WHERE p_user_id IS NOT NULL
      AND (
        (p_space IS DISTINCT FROM 'users' AND a.legacy_allowed_user_id = p_user_id)
        OR (p_space IS DISTINCT FROM 'allowed_users' AND EXISTS (
            SELECT 1
            FROM public.users u
            WHERE u.id = p_user_id
              AND lower(trim(u.email)) = lower(trim(a.primary_email))
        ))
      )
$fn$;

CREATE OR REPLACE FUNCTION pg_temp.dincr_ownership_classification(p_issue TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT CASE
        WHEN p_issue IN ('OK', 'OK_ID_SPACE_COLLISION', 'OK_NO_LEGACY_ID') THEN 'OK'
        WHEN p_issue = 'WORKSPACE_NULL_PARENT_RESOLVABLE' THEN 'SAFE_AUTO_FIX'
        WHEN p_issue IN ('WORKSPACE_MISSING', 'WORKSPACE_OWNER_MISSING') THEN 'ORPHAN'
        ELSE 'NEEDS_REVIEW'
    END
$fn$;

-- Per-row classification. Returns identifiers only: never names, amounts,
-- descriptions or emails. p_include_ok=false returns only rows with an issue
-- (OK_ID_SPACE_COLLISION is returned as informational).
CREATE OR REPLACE FUNCTION pg_temp.dincr_ownership_audit_rows(p_include_ok BOOLEAN DEFAULT FALSE)
RETURNS TABLE (
    table_name TEXT,
    row_id BIGINT,
    issue TEXT,
    classification TEXT,
    workspace_id UUID,
    parent_workspace_id UUID,
    legacy_user_id BIGINT,
    user_id_accounts UUID[]
)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    cfg RECORD;
    has_parent BOOLEAN;
    parent_join TEXT;
    parent_ws TEXT;
    parent_mismatch TEXT;
    parent_resolvable TEXT;
    v_space TEXT;
    v_parent_space TEXT;
BEGIN
    FOR cfg IN SELECT * FROM pg_temp.dincr_ownership_tables() LOOP
        IF pg_catalog.to_regclass(pg_catalog.format('public.%I', cfg.table_name)) IS NULL THEN
            CONTINUE;
        END IF;
        IF (SELECT COUNT(*) FROM information_schema.columns isc
            WHERE isc.table_schema = 'public' AND isc.table_name = cfg.table_name
              AND isc.column_name IN ('user_id', 'workspace_id')) < 2 THEN
            CONTINUE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns isc
                       WHERE isc.table_schema = 'public' AND isc.table_name = cfg.table_name
                         AND isc.column_name = 'id' AND isc.data_type IN ('bigint', 'integer')) THEN
            -- Never skip an ownership table silently.
            RETURN QUERY SELECT cfg.table_name, NULL::BIGINT, 'TABLE_NOT_AUDITABLE'::TEXT, 'NEEDS_REVIEW'::TEXT,
                                NULL::UUID, NULL::UUID, NULL::BIGINT, ARRAY[]::UUID[];
            CONTINUE;
        END IF;

        has_parent := cfg.parent_table IS NOT NULL
            AND pg_catalog.to_regclass(pg_catalog.format('public.%I', cfg.parent_table)) IS NOT NULL;
        v_space := pg_temp.dincr_user_id_space(cfg.table_name);
        v_parent_space := CASE WHEN has_parent THEN pg_temp.dincr_user_id_space(cfg.parent_table) END;

        IF has_parent THEN
            parent_join := pg_catalog.format(
                'LEFT JOIN public.%I p ON p.id = t.%I',
                cfg.parent_table, cfg.parent_column
            );
            parent_ws := 'p.workspace_id';
            parent_mismatch := 'WHEN p.id IS NOT NULL AND p.workspace_id IS DISTINCT FROM t.workspace_id THEN ''PARENT_WORKSPACE_MISMATCH''';
            parent_resolvable := pg_catalog.format($sql$
                WHEN t.workspace_id IS NULL
                     AND p.id IS NOT NULL
                     AND p.workspace_id IS NOT NULL
                     AND EXISTS (SELECT 1 FROM public.workspaces pw
                                 JOIN public.accounts pa ON pa.id = pw.owner_account_id
                                 WHERE pw.id = p.workspace_id)
                     AND (p.user_id IS NULL OR pg_temp.dincr_legacy_id_belongs_to_workspace(p.user_id, p.workspace_id, %L::TEXT))
                     AND t.user_id IS NOT NULL
                     AND pg_temp.dincr_legacy_id_belongs_to_workspace(t.user_id, p.workspace_id, %L::TEXT)
                     -- An id that can denote several accounts (one account's allowed_users.id,
                     -- another's users.id) cannot prove the row's owner: NEEDS_REVIEW.
                     AND cardinality(pg_temp.dincr_legacy_id_accounts(t.user_id, %L::TEXT)) = 1
                THEN 'WORKSPACE_NULL_PARENT_RESOLVABLE'
            $sql$, v_parent_space, v_space, v_space);
        ELSE
            parent_join := '';
            parent_ws := 'NULL::UUID';
            parent_mismatch := '';
            parent_resolvable := '';
        END IF;

        RETURN QUERY EXECUTE pg_catalog.format($sql$
            SELECT *
            FROM (
                SELECT
                    %L::TEXT AS table_name,
                    t.id::BIGINT AS row_id,
                    c.issue,
                    pg_temp.dincr_ownership_classification(c.issue) AS classification,
                    t.workspace_id,
                    %s AS parent_workspace_id,
                    t.user_id::BIGINT AS legacy_user_id,
                    pg_temp.dincr_legacy_id_accounts(t.user_id::BIGINT, %L::TEXT) AS user_id_accounts
                FROM public.%I t
                %s
                LEFT JOIN public.workspaces w ON w.id = t.workspace_id
                LEFT JOIN public.accounts o ON o.id = w.owner_account_id
                CROSS JOIN LATERAL (
                    SELECT CASE
                        %s
                        WHEN t.workspace_id IS NULL THEN 'WORKSPACE_NULL'
                        WHEN w.id IS NULL THEN 'WORKSPACE_MISSING'
                        WHEN o.id IS NULL THEN 'WORKSPACE_OWNER_MISSING'
                        %s
                        -- Canonical rows carry no legacy id: the workspace owns them.
                        WHEN t.user_id IS NULL THEN 'OK_NO_LEGACY_ID'
                        WHEN pg_temp.dincr_legacy_id_belongs_to_workspace(t.user_id::BIGINT, t.workspace_id, %L::TEXT)
                            THEN CASE
                                WHEN cardinality(pg_temp.dincr_legacy_id_accounts(t.user_id::BIGINT, %L::TEXT)) > 1
                                    THEN 'OK_ID_SPACE_COLLISION'
                                ELSE 'OK'
                            END
                        -- The workspace's identity, but in the other space than the FK:
                        -- the FK ties the row to whoever owns that id there, so deleting
                        -- that unrelated person cascades to this row.
                        WHEN pg_temp.dincr_legacy_id_belongs_to_workspace(t.user_id::BIGINT, t.workspace_id)
                            THEN 'USER_ID_WRONG_SPACE'
                        WHEN cardinality(pg_temp.dincr_legacy_id_accounts(t.user_id::BIGINT)) > 0
                            THEN 'USER_ID_FOREIGN'
                        WHEN EXISTS (SELECT 1 FROM public.allowed_users au WHERE au.id = t.user_id)
                          OR EXISTS (SELECT 1 FROM public.users u WHERE u.id = t.user_id)
                            THEN 'USER_ID_UNLINKED'
                        ELSE 'USER_ID_UNRESOLVED'
                    END AS issue
                ) c
            ) r
            WHERE %L OR r.issue <> 'OK'
        $sql$,
            cfg.table_name, parent_ws, v_space, cfg.table_name, parent_join,
            parent_resolvable, parent_mismatch, v_space, v_space, p_include_ok
        );
    END LOOP;

    -- Any table carrying both account_id and workspace_id: the account must own
    -- or be an active member of the workspace.
    FOR cfg IN
        SELECT c1.table_name
        FROM information_schema.columns c1
        JOIN information_schema.columns c2
          ON c2.table_schema = c1.table_schema
         AND c2.table_name = c1.table_name
         AND c2.column_name = 'workspace_id'
        JOIN information_schema.columns c3
          ON c3.table_schema = c1.table_schema
         AND c3.table_name = c1.table_name
         AND c3.column_name = 'id'
        JOIN information_schema.tables it
          ON it.table_schema = c1.table_schema
         AND it.table_name = c1.table_name
         AND it.table_type = 'BASE TABLE'
        WHERE c1.table_schema = 'public'
          AND c1.table_name <> 'workspace_members'
          AND c1.column_name = 'account_id'
          AND c1.data_type = 'uuid'
          AND c2.data_type = 'uuid'
          AND c3.data_type IN ('bigint', 'integer')
        ORDER BY c1.table_name
    LOOP
        RETURN QUERY EXECUTE pg_catalog.format($sql$
            SELECT %L::TEXT, t.id::BIGINT,
                   CASE
                       WHEN t.workspace_id IS NULL THEN 'WORKSPACE_NULL'
                       WHEN w.id IS NULL THEN 'WORKSPACE_MISSING'
                       ELSE 'ACCOUNT_NOT_IN_WORKSPACE'
                   END,
                   pg_temp.dincr_ownership_classification(
                       CASE
                           WHEN t.workspace_id IS NULL THEN 'WORKSPACE_NULL'
                           WHEN w.id IS NULL THEN 'WORKSPACE_MISSING'
                           ELSE 'ACCOUNT_NOT_IN_WORKSPACE'
                       END),
                   t.workspace_id, NULL::UUID, NULL::BIGINT, ARRAY[t.account_id]::UUID[]
            FROM public.%I t
            LEFT JOIN public.workspaces w ON w.id = t.workspace_id
            WHERE t.account_id IS NOT NULL
              AND (
                  t.workspace_id IS NULL
                  OR w.id IS NULL
                  OR NOT (
                      w.owner_account_id = t.account_id
                      OR EXISTS (SELECT 1 FROM public.workspace_members wm
                                 WHERE wm.workspace_id = t.workspace_id
                                   AND wm.account_id = t.account_id
                                   AND wm.status = 'active')
                  )
              )
        $sql$, cfg.table_name, cfg.table_name);
    END LOOP;

    -- A FK from a dual-space user_id to users/allowed_users is a cascade risk:
    -- deleting an unrelated person in that space deletes rows that carry the same
    -- integer from the other space. Informational until the FKs are retired.
    RETURN QUERY
    SELECT child.relname::TEXT, NULL::BIGINT,
           ('USER_ID_FK_TO_' || upper(parent.relname) || '_ON_DELETE_' ||
            CASE c.confdeltype WHEN 'c' THEN 'CASCADE' WHEN 'n' THEN 'SET_NULL' WHEN 'r' THEN 'RESTRICT'
                               WHEN 'd' THEN 'SET_DEFAULT' ELSE 'NO_ACTION' END)::TEXT,
           -- With every row in the FK's own space (USER_ID_WRONG_SPACE is NEEDS_REVIEW
           -- and the guard rejects new ones) a cascade only removes the deleted
           -- person's own rows. Informational until Phase E drops these FKs.
           'INFO'::TEXT,
           NULL::UUID, NULL::UUID, NULL::BIGINT, ARRAY[]::UUID[]
    FROM pg_catalog.pg_constraint c
    JOIN pg_catalog.pg_class child ON child.oid = c.conrelid
    JOIN pg_catalog.pg_namespace ns ON ns.oid = child.relnamespace AND ns.nspname = 'public'
    JOIN pg_catalog.pg_class parent ON parent.oid = c.confrelid
    JOIN pg_catalog.pg_namespace pns ON pns.oid = parent.relnamespace AND pns.nspname = 'public'
    JOIN pg_catalog.pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND cardinality(c.conkey) = 1 AND att.attname = 'user_id'
      AND parent.relname IN ('users', 'allowed_users')
      AND child.relname IN (SELECT o.table_name FROM pg_temp.dincr_ownership_tables() o);

    -- Tables that store a legacy id to write with later (mail connections): a
    -- background sync writes that id into the financial tables, so it must be an
    -- identity of the connection's workspace or every synced write is rejected.
    FOR cfg IN
        SELECT c1.table_name
        FROM information_schema.columns c1
        JOIN information_schema.columns c2
          ON c2.table_schema = c1.table_schema AND c2.table_name = c1.table_name
         AND c2.column_name = 'workspace_id' AND c2.data_type = 'uuid'
        JOIN information_schema.columns c3
          ON c3.table_schema = c1.table_schema AND c3.table_name = c1.table_name
         AND c3.column_name = 'id' AND c3.data_type IN ('bigint', 'integer')
        WHERE c1.table_schema = 'public'
          AND c1.column_name = 'legacy_user_id'
        ORDER BY c1.table_name
    LOOP
        RETURN QUERY EXECUTE pg_catalog.format($sql$
            SELECT %L::TEXT, t.id::BIGINT, 'LEGACY_USER_ID_NOT_IN_WORKSPACE', 'NEEDS_REVIEW',
                   t.workspace_id, NULL::UUID, t.legacy_user_id::BIGINT,
                   pg_temp.dincr_legacy_id_accounts(t.legacy_user_id::BIGINT, 'users')
            FROM public.%I t
            WHERE t.workspace_id IS NOT NULL
              -- legacy_user_id columns are users.id (FK -> users) everywhere.
              AND NOT pg_temp.dincr_legacy_id_belongs_to_workspace(t.legacy_user_id::BIGINT, t.workspace_id, 'users')
        $sql$, cfg.table_name, cfg.table_name);
    END LOOP;
END
$fn$;

-- Identity core checks (accounts / workspaces / legacy bridges). Identifiers only.
CREATE OR REPLACE FUNCTION pg_temp.dincr_identity_audit()
RETURNS TABLE (check_name TEXT, subject_id TEXT, classification TEXT)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT 'WORKSPACE_OWNER_MISSING', w.id::TEXT, 'ORPHAN'
    FROM public.workspaces w
    WHERE NOT EXISTS (SELECT 1 FROM public.accounts a WHERE a.id = w.owner_account_id)
    UNION ALL
    SELECT 'WORKSPACE_OWNER_NOT_MEMBER', w.id::TEXT, 'NEEDS_REVIEW'
    FROM public.workspaces w
    WHERE NOT EXISTS (SELECT 1 FROM public.workspace_members wm
                      WHERE wm.workspace_id = w.id AND wm.account_id = w.owner_account_id
                        AND wm.status = 'active')
    UNION ALL
    SELECT 'PERSONAL_WORKSPACE_KEY_MISMATCH', w.id::TEXT, 'NEEDS_REVIEW'
    FROM public.workspaces w
    WHERE w.workspace_type = 'personal'
      AND w.workspace_key IS DISTINCT FROM 'personal:' || w.owner_account_id::TEXT
    UNION ALL
    SELECT 'ACCOUNT_PERSONAL_WORKSPACE_COUNT', a.id::TEXT, 'NEEDS_REVIEW'
    FROM public.accounts a
    WHERE (SELECT COUNT(*) FROM public.workspaces w
           WHERE w.owner_account_id = a.id AND w.workspace_type = 'personal') <> 1
    UNION ALL
    SELECT 'ACCOUNT_LEGACY_ID_NULL', a.id::TEXT, 'NEEDS_REVIEW'
    FROM public.accounts a
    WHERE a.legacy_allowed_user_id IS NULL
    UNION ALL
    SELECT 'ACCOUNT_LEGACY_ID_DANGLING', a.id::TEXT, 'ORPHAN'
    FROM public.accounts a
    WHERE a.legacy_allowed_user_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM public.allowed_users au WHERE au.id = a.legacy_allowed_user_id)
    UNION ALL
    SELECT 'ACCOUNT_ALLOWED_USER_EMAIL_MISMATCH', a.id::TEXT, 'NEEDS_REVIEW'
    FROM public.accounts a
    JOIN public.allowed_users au ON au.id = a.legacy_allowed_user_id
    WHERE lower(trim(au.email)) IS DISTINCT FROM lower(trim(a.primary_email))
    UNION ALL
    SELECT 'ACCOUNT_AUTH_ID_MISMATCH', a.id::TEXT, 'NEEDS_REVIEW'
    FROM public.accounts a
    JOIN public.allowed_users au ON au.id = a.legacy_allowed_user_id
    WHERE a.supabase_user_id IS NOT NULL
      AND NULLIF(lower(trim(au.supabase_user_id)), '') IS NOT NULL
      AND lower(trim(au.supabase_user_id)) <> lower(a.supabase_user_id::TEXT)
    UNION ALL
    SELECT 'ACTIVE_ALLOWED_USER_WITHOUT_ACCOUNT', au.id::TEXT, 'NEEDS_REVIEW'
    FROM public.allowed_users au
    WHERE au.status = 'active'
      AND NOT EXISTS (SELECT 1 FROM public.accounts a WHERE a.legacy_allowed_user_id = au.id)
    UNION ALL
    SELECT 'USERS_ROW_WITHOUT_ACCOUNT', u.id::TEXT, 'INFO'
    FROM public.users u
    WHERE NOT EXISTS (SELECT 1 FROM public.accounts a WHERE lower(a.primary_email) = lower(u.email))
    UNION ALL
    SELECT 'ACCOUNT_WITHOUT_USERS_ROW', a.id::TEXT, 'INFO'
    FROM public.accounts a
    WHERE NOT EXISTS (SELECT 1 FROM public.users u WHERE lower(trim(u.email)) = lower(trim(a.primary_email)))
$fn$;

CREATE OR REPLACE FUNCTION pg_temp.dincr_ownership_audit_summary()
RETURNS TABLE (table_name TEXT, classification TEXT, issue TEXT, row_count BIGINT)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT r.table_name, r.classification, r.issue, COUNT(*)::BIGINT
    FROM pg_temp.dincr_ownership_audit_rows(TRUE) r
    GROUP BY r.table_name, r.classification, r.issue
    UNION ALL
    SELECT '_identity', i.classification, i.check_name, COUNT(*)::BIGINT
    FROM pg_temp.dincr_identity_audit() i
    GROUP BY i.classification, i.check_name
    ORDER BY 1, 2, 3
$fn$;
-- END DINCR OWNERSHIP AUDIT FUNCTIONS

SET LOCAL transaction_read_only = on;

SELECT 'summary' AS section, s.table_name AS subject, NULL::BIGINT AS row_id,
       s.classification, s.issue, s.row_count::TEXT AS detail
FROM pg_temp.dincr_ownership_audit_summary() s
UNION ALL
SELECT 'row', r.table_name, r.row_id, r.classification, r.issue,
       jsonb_build_object(
           'workspace_id', r.workspace_id,
           'parent_workspace_id', r.parent_workspace_id,
           'legacy_user_id', r.legacy_user_id,
           'user_id_accounts', r.user_id_accounts
       )::TEXT
FROM pg_temp.dincr_ownership_audit_rows(FALSE) r
UNION ALL
SELECT 'identity', i.check_name, NULL, i.classification, i.check_name, i.subject_id
FROM pg_temp.dincr_identity_audit() i
UNION ALL
SELECT 'user_id_only_table', c.table_name, NULL, 'INFO', 'NO_WORKSPACE_ID', NULL
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'
WHERE c.table_schema = 'public' AND c.column_name = 'user_id'
  AND NOT EXISTS (SELECT 1 FROM information_schema.columns w
                  WHERE w.table_schema = 'public' AND w.table_name = c.table_name
                    AND w.column_name = 'workspace_id')
UNION ALL
SELECT 'unguarded_table', c.table_name, NULL, 'INFO', 'USER_ID_AND_WORKSPACE_NOT_GUARDED', NULL
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'
WHERE c.table_schema = 'public' AND c.column_name = 'user_id'
  AND EXISTS (SELECT 1 FROM information_schema.columns w
              WHERE w.table_schema = 'public' AND w.table_name = c.table_name
                AND w.column_name = 'workspace_id')
  AND c.table_name NOT IN (SELECT table_name FROM pg_temp.dincr_ownership_tables())
UNION ALL
SELECT 'user_id_fk', child.relname, NULL, 'INFO', c.conname,
       parent.relname || ' ON DELETE ' || CASE c.confdeltype
           WHEN 'c' THEN 'CASCADE' WHEN 'n' THEN 'SET NULL' WHEN 'r' THEN 'RESTRICT'
           WHEN 'd' THEN 'SET DEFAULT' ELSE 'NO ACTION' END
       || CASE WHEN c.convalidated THEN '' ELSE ' (NOT VALID)' END
FROM pg_constraint c
JOIN pg_class child ON child.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = child.relnamespace AND ns.nspname = 'public'
JOIN pg_class parent ON parent.oid = c.confrelid
JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
WHERE c.contype = 'f' AND cardinality(c.conkey) = 1 AND att.attname = 'user_id'
  AND child.relname IN (SELECT table_name FROM pg_temp.dincr_ownership_tables())
ORDER BY 1, 2, 3, 4, 5;
