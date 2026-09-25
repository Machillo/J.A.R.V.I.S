-- DINCR pre-release financial ownership integrity (prepared, NOT applied).
--
-- HUMAN GATE: run database/audits/financial_ownership_preflight.sql first and
-- review every NEEDS_REVIEW / ORPHAN row with a human. Only then apply this file.
--
-- Background (see the PR for the full audit):
--   * Ownership is workspace_id. Reads and writes are scoped by workspace_id.
--   * The legacy user_id column has TWO id spaces:
--       - allowed_users.id  (Owner/Personal writers, payroll overtime, DEFAULT 1);
--       - users.id          (DINCR Users writers: _legacy_financial_user_id and the
--                            mail candidates, resolved by the account email).
--     A row is consistent when its user_id is an identity, in EITHER space, of an
--     account that owns or is an active member of the row's workspace.
--   * Therefore "SET user_id = owner.legacy_allowed_user_id" is NOT a safe repair:
--     for DINCR rows it would point user_id at another person's users row.
--
-- What this migration does:
--   1. Aborts if the identity core is inconsistent (workspace without owner,
--      account with several personal workspaces, personal key mismatch).
--   2. Installs read-only audit functions (same bodies as the preflight file).
--   3. Records a before/after classification snapshot (counts only).
--   4. Repairs ONLY the SAFE_AUTO_FIX class: a child row (e.g. debt_payments)
--      with workspace_id NULL whose parent row has a valid workspace AND whose own
--      user_id and the parent's user_id both belong to that workspace. Every change
--      is written to financial_ownership_repair_log (old/new value) first.
--   5. Prevents new inconsistencies for new writes:
--      - CHECK (workspace_id IS NOT NULL) NOT VALID;
--      - child (parent_id, workspace_id) -> parent (id, workspace_id) FK NOT VALID;
--      - trigger rejecting a user_id that does not belong to the row's workspace
--        and any move of an existing row to another workspace. It fires on INSERT
--        and on UPDATE OF user_id/workspace_id, and ignores updates that leave both
--        unchanged, so rows under review that HAVE a workspace stay editable.
--        Rows with a NULL workspace are invisible to the app (every query is
--        workspace-scoped) and the NOT VALID CHECK rejects any update of them:
--        they are resolved by a human, with the guards disabled in that session.
--
-- What it deliberately does NOT do: it never changes user_id, never assigns a
-- workspace from user_id alone (the Phase 2A mapping is ambiguous across id
-- spaces), never deletes, never validates the NOT VALID constraints, and never
-- touches NEEDS_REVIEW / ORPHAN rows. Idempotent: a second run repairs nothing.

BEGIN;
-- Fail fast instead of queueing behind application traffic.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

-- ---------------------------------------------------------------------------
-- 0. Preflight: identity core must exist.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.accounts') IS NULL
       OR to_regclass('public.workspaces') IS NULL
       OR to_regclass('public.workspace_members') IS NULL
       OR to_regclass('public.allowed_users') IS NULL
       OR to_regclass('public.users') IS NULL THEN
        RAISE EXCEPTION 'financial ownership integrity: identity tables missing, aborting';
    END IF;
    IF current_setting('server_version_num')::INT < 140000 THEN
        RAISE EXCEPTION 'financial ownership integrity: PostgreSQL 14+ required, aborting';
    END IF;
END $$;

-- BEGIN DINCR OWNERSHIP AUDIT FUNCTIONS
CREATE OR REPLACE FUNCTION public.dincr_ownership_tables()
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

-- True when p_user_id is, in either legacy id space, an identity of an account
-- that owns or is an active member of p_workspace_id.
CREATE OR REPLACE FUNCTION public.dincr_legacy_id_belongs_to_workspace(p_user_id BIGINT, p_workspace_id UUID)
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
        WHERE a.legacy_allowed_user_id = p_user_id
           OR EXISTS (
                SELECT 1
                FROM public.users u
                WHERE u.id = p_user_id
                  AND lower(trim(u.email)) = lower(trim(a.primary_email))
           )
    )
$fn$;

-- Every account that p_user_id can denote, in either legacy id space.
CREATE OR REPLACE FUNCTION public.dincr_legacy_id_accounts(p_user_id BIGINT)
RETURNS UUID[]
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT COALESCE(array_agg(DISTINCT a.id ORDER BY a.id), ARRAY[]::UUID[])
    FROM public.accounts a
    WHERE p_user_id IS NOT NULL
      AND (
        a.legacy_allowed_user_id = p_user_id
        OR EXISTS (
            SELECT 1
            FROM public.users u
            WHERE u.id = p_user_id
              AND lower(trim(u.email)) = lower(trim(a.primary_email))
        )
      )
$fn$;

CREATE OR REPLACE FUNCTION public.dincr_ownership_classification(p_issue TEXT)
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
CREATE OR REPLACE FUNCTION public.dincr_ownership_audit_rows(p_include_ok BOOLEAN DEFAULT FALSE)
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
BEGIN
    FOR cfg IN SELECT * FROM public.dincr_ownership_tables() LOOP
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

        IF has_parent THEN
            parent_join := pg_catalog.format(
                'LEFT JOIN public.%I p ON p.id = t.%I',
                cfg.parent_table, cfg.parent_column
            );
            parent_ws := 'p.workspace_id';
            parent_mismatch := 'WHEN p.id IS NOT NULL AND p.workspace_id IS DISTINCT FROM t.workspace_id THEN ''PARENT_WORKSPACE_MISMATCH''';
            parent_resolvable := $sql$
                WHEN t.workspace_id IS NULL
                     AND p.id IS NOT NULL
                     AND p.workspace_id IS NOT NULL
                     AND EXISTS (SELECT 1 FROM public.workspaces pw
                                 JOIN public.accounts pa ON pa.id = pw.owner_account_id
                                 WHERE pw.id = p.workspace_id)
                     AND (p.user_id IS NULL OR public.dincr_legacy_id_belongs_to_workspace(p.user_id, p.workspace_id))
                     AND t.user_id IS NOT NULL
                     AND public.dincr_legacy_id_belongs_to_workspace(t.user_id, p.workspace_id)
                     -- A colliding id (one account's allowed_users.id, another's users.id)
                     -- cannot prove the row's owner: those rows stay NEEDS_REVIEW.
                     AND cardinality(public.dincr_legacy_id_accounts(t.user_id)) = 1
                THEN 'WORKSPACE_NULL_PARENT_RESOLVABLE'
            $sql$;
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
                    public.dincr_ownership_classification(c.issue) AS classification,
                    t.workspace_id,
                    %s AS parent_workspace_id,
                    t.user_id::BIGINT AS legacy_user_id,
                    public.dincr_legacy_id_accounts(t.user_id::BIGINT) AS user_id_accounts
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
                        WHEN public.dincr_legacy_id_belongs_to_workspace(t.user_id::BIGINT, t.workspace_id)
                            THEN CASE
                                WHEN cardinality(public.dincr_legacy_id_accounts(t.user_id::BIGINT)) > 1
                                    THEN 'OK_ID_SPACE_COLLISION'
                                ELSE 'OK'
                            END
                        WHEN cardinality(public.dincr_legacy_id_accounts(t.user_id::BIGINT)) > 0
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
            cfg.table_name, parent_ws, cfg.table_name, parent_join,
            parent_resolvable, parent_mismatch, p_include_ok
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
                   public.dincr_ownership_classification(
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
           'INFO'::TEXT, NULL::UUID, NULL::UUID, NULL::BIGINT, ARRAY[]::UUID[]
    FROM pg_catalog.pg_constraint c
    JOIN pg_catalog.pg_class child ON child.oid = c.conrelid
    JOIN pg_catalog.pg_namespace ns ON ns.oid = child.relnamespace AND ns.nspname = 'public'
    JOIN pg_catalog.pg_class parent ON parent.oid = c.confrelid
    JOIN pg_catalog.pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND cardinality(c.conkey) = 1 AND att.attname = 'user_id'
      AND parent.relname IN ('users', 'allowed_users')
      AND child.relname IN (SELECT o.table_name FROM public.dincr_ownership_tables() o);

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
                   public.dincr_legacy_id_accounts(t.legacy_user_id::BIGINT)
            FROM public.%I t
            WHERE t.workspace_id IS NOT NULL
              AND NOT public.dincr_legacy_id_belongs_to_workspace(t.legacy_user_id::BIGINT, t.workspace_id)
        $sql$, cfg.table_name, cfg.table_name);
    END LOOP;
END
$fn$;

-- Identity core checks (accounts / workspaces / legacy bridges). Identifiers only.
CREATE OR REPLACE FUNCTION public.dincr_identity_audit()
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

CREATE OR REPLACE FUNCTION public.dincr_ownership_audit_summary()
RETURNS TABLE (table_name TEXT, classification TEXT, issue TEXT, row_count BIGINT)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT r.table_name, r.classification, r.issue, COUNT(*)::BIGINT
    FROM public.dincr_ownership_audit_rows(TRUE) r
    GROUP BY r.table_name, r.classification, r.issue
    UNION ALL
    SELECT '_identity', i.classification, i.check_name, COUNT(*)::BIGINT
    FROM public.dincr_identity_audit() i
    GROUP BY i.classification, i.check_name
    ORDER BY 1, 2, 3
$fn$;
-- END DINCR OWNERSHIP AUDIT FUNCTIONS

REVOKE ALL ON FUNCTION public.dincr_ownership_tables() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dincr_legacy_id_belongs_to_workspace(BIGINT, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dincr_legacy_id_accounts(BIGINT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dincr_ownership_classification(TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dincr_ownership_audit_rows(BOOLEAN) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dincr_identity_audit() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.dincr_ownership_audit_summary() FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 1. Audit storage: counts snapshots and a before/after log of every repair.
--    Identifiers only; no names, amounts or descriptions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.financial_ownership_audit_snapshots (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('before', 'after')),
    table_name TEXT NOT NULL,
    classification TEXT NOT NULL,
    issue TEXT NOT NULL,
    row_count BIGINT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.financial_ownership_repair_log (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    table_name TEXT NOT NULL,
    row_id BIGINT NOT NULL,
    column_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_financial_ownership_repair_log_row
    ON public.financial_ownership_repair_log(table_name, row_id);

ALTER TABLE public.financial_ownership_audit_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.financial_ownership_repair_log ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.financial_ownership_audit_snapshots FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.financial_ownership_repair_log FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON SEQUENCE public.financial_ownership_audit_snapshots_id_seq FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON SEQUENCE public.financial_ownership_repair_log_id_seq FROM anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. Abort on an inconsistent identity core, snapshot, repair SAFE_AUTO_FIX only.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_run UUID := gen_random_uuid();
    v_blocking BIGINT;
    v_repaired BIGINT := 0;
    v_count BIGINT;
    cfg RECORD;
BEGIN
    SELECT COUNT(*) INTO v_blocking
    FROM public.dincr_identity_audit()
    WHERE check_name IN (
        'WORKSPACE_OWNER_MISSING',
        'PERSONAL_WORKSPACE_KEY_MISMATCH',
        'ACCOUNT_PERSONAL_WORKSPACE_COUNT'
    );
    IF v_blocking > 0 THEN
        RAISE EXCEPTION 'financial ownership integrity: % identity-core inconsistencies, aborting (run the preflight)', v_blocking;
    END IF;

    -- A stored mail-connection id outside its workspace would make every synced
    -- write fail after the guard is installed: fix it first.
    SELECT COUNT(*) INTO v_blocking
    FROM public.dincr_ownership_audit_rows(FALSE)
    WHERE issue = 'LEGACY_USER_ID_NOT_IN_WORKSPACE';
    IF v_blocking > 0 THEN
        RAISE EXCEPTION 'financial ownership integrity: % stored legacy ids outside their workspace, aborting (run the preflight)', v_blocking;
    END IF;

    INSERT INTO public.financial_ownership_audit_snapshots(run_id, phase, table_name, classification, issue, row_count)
    SELECT v_run, 'before', s.table_name, s.classification, s.issue, s.row_count
    FROM public.dincr_ownership_audit_summary() s;

    FOR cfg IN
        SELECT t.table_name, t.parent_table, t.parent_column
        FROM public.dincr_ownership_tables() t
        WHERE t.parent_table IS NOT NULL
    LOOP
        IF to_regclass(format('public.%I', cfg.table_name)) IS NULL
           OR to_regclass(format('public.%I', cfg.parent_table)) IS NULL THEN
            CONTINUE;
        END IF;

        -- Re-derives the SAFE_AUTO_FIX predicate on the live rows (not on a
        -- snapshot) and logs old/new values before they change.
        EXECUTE format($sql$
            WITH candidates AS (
                SELECT a.row_id, a.parent_workspace_id
                FROM public.dincr_ownership_audit_rows(FALSE) a
                WHERE a.table_name = %L
                  AND a.classification = 'SAFE_AUTO_FIX'
            ),
            changed AS (
                UPDATE public.%I t
                   SET workspace_id = c.parent_workspace_id
                  FROM candidates c
                 WHERE t.id = c.row_id
                   AND t.workspace_id IS NULL
                RETURNING t.id, t.workspace_id
            )
            INSERT INTO public.financial_ownership_repair_log(run_id, table_name, row_id, column_name, old_value, new_value, reason)
            SELECT %L::UUID, %L, ch.id, 'workspace_id', NULL, ch.workspace_id::TEXT, 'WORKSPACE_NULL_PARENT_RESOLVABLE'
            FROM changed ch
        $sql$, cfg.table_name, cfg.table_name, v_run, cfg.table_name);
        GET DIAGNOSTICS v_count = ROW_COUNT;
        v_repaired := v_repaired + v_count;
    END LOOP;

    INSERT INTO public.financial_ownership_audit_snapshots(run_id, phase, table_name, classification, issue, row_count)
    SELECT v_run, 'after', s.table_name, s.classification, s.issue, s.row_count
    FROM public.dincr_ownership_audit_summary() s;

    -- Postflight: nothing auto-fixable may remain.
    SELECT COUNT(*) INTO v_count
    FROM public.dincr_ownership_audit_rows(FALSE)
    WHERE classification = 'SAFE_AUTO_FIX';
    IF v_count > 0 THEN
        RAISE EXCEPTION 'financial ownership integrity: % SAFE_AUTO_FIX rows remain after repair, aborting', v_count;
    END IF;

    RAISE NOTICE 'financial ownership integrity run %: repaired % rows', v_run, v_repaired;
END $$;

-- ---------------------------------------------------------------------------
-- 3. Prevention for new writes (NOT VALID: existing rows are not re-checked;
--    validate only after every NEEDS_REVIEW row has been resolved by a human).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.dincr_guard_financial_ownership()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    -- Transitional guard. Ownership is workspace_id; the legacy user_id only has
    -- to agree with it. NULL workspace is rejected by the table's CHECK. A NULL
    -- user_id is the canonical future (no legacy attribution) and is accepted;
    -- the column's NOT NULL keeps rejecting it until legacy writers are retired.
    IF TG_OP = 'UPDATE' THEN
        -- Moving a row to another workspace is a reviewed data operation, never a
        -- side effect of an application write (run it with this trigger disabled).
        IF OLD.workspace_id IS NOT NULL AND NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
            RAISE EXCEPTION 'financial ownership change on %', TG_TABLE_NAME
                USING ERRCODE = '23514',
                      HINT = 'rows are not moved between workspaces by application writes';
        END IF;
        -- Unchanged legacy ids (e.g. an upsert rewriting the same values) keep rows
        -- under review editable.
        IF NEW.user_id IS NOT DISTINCT FROM OLD.user_id
           AND NEW.workspace_id IS NOT DISTINCT FROM OLD.workspace_id THEN
            RETURN NEW;
        END IF;
    END IF;
    IF NEW.workspace_id IS NULL OR NEW.user_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT public.dincr_legacy_id_belongs_to_workspace(NEW.user_id::BIGINT, NEW.workspace_id) THEN
        -- No identifiers or values in the message: it can reach logs.
        RAISE EXCEPTION 'financial ownership mismatch on %', TG_TABLE_NAME
            USING ERRCODE = '23514',
                  HINT = 'user_id must be an identity of an owner or active member of workspace_id';
    END IF;
    RETURN NEW;
END
$fn$;
REVOKE ALL ON FUNCTION public.dincr_guard_financial_ownership() FROM PUBLIC, anon, authenticated;

DO $$
DECLARE
    cfg RECORD;
    v_name TEXT;
BEGIN
    FOR cfg IN SELECT * FROM public.dincr_ownership_tables() LOOP
        IF to_regclass(format('public.%I', cfg.table_name)) IS NULL THEN
            CONTINUE;
        END IF;
        IF (SELECT COUNT(*) FROM information_schema.columns isc
            WHERE isc.table_schema = 'public' AND isc.table_name = cfg.table_name
              AND isc.column_name IN ('user_id', 'workspace_id')) < 2 THEN
            CONTINUE;
        END IF;

        v_name := 'ck_' || cfg.table_name || '_workspace_required';
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = v_name AND conrelid = format('public.%I', cfg.table_name)::regclass
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (workspace_id IS NOT NULL) NOT VALID',
                cfg.table_name, v_name
            );
        END IF;

        EXECUTE format(
            'CREATE OR REPLACE TRIGGER %I BEFORE INSERT OR UPDATE OF user_id, workspace_id ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.dincr_guard_financial_ownership()',
            'trg_' || cfg.table_name || '_ownership_guard', cfg.table_name
        );

        IF cfg.parent_table IS NOT NULL
           AND to_regclass(format('public.%I', cfg.parent_table)) IS NOT NULL THEN
            IF to_regclass(format('public.%I', 'uq_' || cfg.parent_table || '_id_workspace')) IS NULL THEN
                EXECUTE format(
                    'CREATE UNIQUE INDEX %I ON public.%I(id, workspace_id)',
                    'uq_' || cfg.parent_table || '_id_workspace', cfg.parent_table
                );
                -- Marker: the rollback only drops indexes this migration created.
                EXECUTE format('COMMENT ON INDEX public.%I IS %L',
                    'uq_' || cfg.parent_table || '_id_workspace', 'dincr-ownership-guard');
            END IF;
            v_name := 'fk_' || cfg.table_name || '_parent_workspace';
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = v_name AND conrelid = format('public.%I', cfg.table_name)::regclass
            ) THEN
                EXECUTE format(
                    'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (%I, workspace_id) '
                    -- NO ACTION (checked at statement end) never changes how the
                    -- existing single-column FK already deletes or nulls children.
                    'REFERENCES public.%I(id, workspace_id) NOT VALID',
                    cfg.table_name, v_name, cfg.parent_column, cfg.parent_table
                );
            END IF;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 4. Postflight: prevention is installed on every existing target table.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_missing BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_missing
    FROM public.dincr_ownership_tables() t
    WHERE to_regclass(format('public.%I', t.table_name)) IS NOT NULL
      AND (SELECT COUNT(*) FROM information_schema.columns isc
           WHERE isc.table_schema = 'public' AND isc.table_name = t.table_name
             AND isc.column_name IN ('user_id', 'workspace_id')) = 2
      AND (
        NOT EXISTS (SELECT 1 FROM pg_trigger tr
                    WHERE tr.tgrelid = format('public.%I', t.table_name)::regclass
                      AND tr.tgname = 'trg_' || t.table_name || '_ownership_guard')
        OR NOT EXISTS (SELECT 1 FROM pg_constraint c
                       WHERE c.conrelid = format('public.%I', t.table_name)::regclass
                         AND c.conname = 'ck_' || t.table_name || '_workspace_required')
      );
    IF v_missing > 0 THEN
        RAISE EXCEPTION 'financial ownership integrity: prevention missing on % tables, aborting', v_missing;
    END IF;
END $$;

COMMIT;

-- Recovery (manual, human decision): database/rollback/
-- 20260925120000_financial_ownership_integrity_rollback.sql removes the guards and,
-- optionally, reverts the logged repairs of one run (tested in
-- backend/tests/test_financial_ownership_integrity_pg.py).
