-- Phase 4D: global workspace hardening for JARVIS Personal.
-- Preconditions: all prior workspace backfills have completed with zero unmapped rows.
-- Non-destructive with respect to business data: no rows or legacy user_id columns are removed.

DO $$
DECLARE
    r RECORD;
    missing_count BIGINT;
BEGIN
    FOR r IN
        SELECT c.table_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.column_name = 'workspace_id'
          AND c.table_name <> 'workspaces'
        ORDER BY c.table_name
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I WHERE workspace_id IS NULL', r.table_name)
        INTO missing_count;

        IF missing_count > 0 THEN
            RAISE EXCEPTION 'Cannot harden %.workspace_id: % rows are still unmapped', r.table_name, missing_count;
        END IF;

        EXECUTE format('ALTER TABLE %I ALTER COLUMN workspace_id SET NOT NULL', r.table_name);
    END LOOP;
END $$;

-- Workspace-native uniqueness used by modules that can eventually coexist in
-- multiple workspaces owned by the same account. Legacy user_id constraints are
-- intentionally retained for compatibility during the transition.
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_preferences_workspace_key
    ON user_preferences(workspace_id, preference_key);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_subscriptions_workspace_channel_endpoint
    ON notification_subscriptions(workspace_id, channel, endpoint);

CREATE UNIQUE INDEX IF NOT EXISTS uq_card_aliases_workspace_last4
    ON card_aliases(workspace_id, card_last4);

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_monitor_settings_workspace
    ON email_monitor_settings(workspace_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_messages_workspace_provider_message
    ON email_ingested_messages(workspace_id, provider, provider_message_id)
    WHERE provider_message_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_messages_workspace_fingerprint
    ON email_ingested_messages(workspace_id, fingerprint)
    WHERE fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_candidates_workspace_fingerprint
    ON email_transaction_candidates(workspace_id, fingerprint)
    WHERE fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_statement_workspace_message
    ON email_statement_documents(workspace_id, email_message_id);

-- Validate all workspace foreign keys that were intentionally created NOT VALID
-- during the non-destructive migration phases.
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT
            n.nspname AS schema_name,
            c.relname AS table_name,
            con.conname AS constraint_name
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND con.contype = 'f'
          AND con.convalidated = FALSE
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS key(attnum)
              JOIN pg_attribute a
                ON a.attrelid = con.conrelid
               AND a.attnum = key.attnum
              WHERE a.attname = 'workspace_id'
          )
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I VALIDATE CONSTRAINT %I',
            r.schema_name,
            r.table_name,
            r.constraint_name
        );
    END LOOP;
END $$;

-- Final audit. The migration intentionally fails before this point if any
-- workspace-aware table still contains an unmapped row.
WITH workspace_tables AS (
    SELECT DISTINCT c.table_name
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.column_name = 'workspace_id'
      AND c.table_name <> 'workspaces'
), audit AS (
    SELECT COUNT(*)::BIGINT AS table_count
    FROM workspace_tables
)
SELECT
    audit.table_count AS workspace_tables_hardened,
    0::BIGINT AS unmapped_rows_remaining
FROM audit;
