-- JARVIS Personal - Phase 4B: Email Monitor workspace hardening
-- Non-destructive: keeps legacy user_id while adding/backfilling workspace_id.

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'email_monitor_settings',
        'email_ingested_messages',
        'email_transaction_candidates',
        'email_statement_documents',
        'card_aliases',
        'email_parser_logs'
    ]
    LOOP
        IF to_regclass(tbl) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS workspace_id UUID', tbl);
        END IF;
    END LOOP;
END $$;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'email_monitor_settings',
        'email_ingested_messages',
        'email_transaction_candidates',
        'email_statement_documents',
        'card_aliases',
        'email_parser_logs'
    ]
    LOOP
        IF to_regclass(tbl) IS NOT NULL THEN
            EXECUTE format($sql$
                UPDATE %I target
                SET workspace_id = mapped.workspace_id
                FROM (
                    SELECT a.legacy_allowed_user_id AS legacy_user_id,
                           (
                               SELECT w.id
                               FROM workspaces w
                               WHERE w.owner_account_id = a.id
                                 AND w.workspace_type = 'personal'
                               ORDER BY w.created_at, w.id
                               LIMIT 1
                           ) AS workspace_id
                    FROM accounts a
                ) mapped
                WHERE target.workspace_id IS NULL
                  AND target.user_id = mapped.legacy_user_id
                  AND mapped.workspace_id IS NOT NULL
            $sql$, tbl);
        END IF;
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_email_monitor_settings_workspace ON email_monitor_settings(workspace_id);
CREATE INDEX IF NOT EXISTS idx_email_ingested_messages_workspace_created ON email_ingested_messages(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_candidates_workspace_status_created ON email_transaction_candidates(workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_statement_documents_workspace ON email_statement_documents(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_card_aliases_workspace ON card_aliases(workspace_id);
CREATE INDEX IF NOT EXISTS idx_email_parser_logs_workspace_created ON email_parser_logs(workspace_id, created_at DESC);

DO $$
DECLARE
    tbl TEXT;
    cname TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'email_monitor_settings',
        'email_ingested_messages',
        'email_transaction_candidates',
        'email_statement_documents',
        'card_aliases',
        'email_parser_logs'
    ]
    LOOP
        IF to_regclass(tbl) IS NOT NULL THEN
            cname := tbl || '_workspace_id_fkey';
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = cname) THEN
                EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE NOT VALID', tbl, cname);
            END IF;
        END IF;
    END LOOP;
END $$;

SELECT
    (SELECT COUNT(*) FROM email_monitor_settings WHERE workspace_id IS NULL) AS settings_unmapped,
    (SELECT COUNT(*) FROM email_ingested_messages WHERE workspace_id IS NULL) AS messages_unmapped,
    (SELECT COUNT(*) FROM email_transaction_candidates WHERE workspace_id IS NULL) AS candidates_unmapped,
    (SELECT COUNT(*) FROM email_statement_documents WHERE workspace_id IS NULL) AS statements_unmapped,
    (SELECT COUNT(*) FROM card_aliases WHERE workspace_id IS NULL) AS card_aliases_unmapped,
    (SELECT COUNT(*) FROM email_parser_logs WHERE workspace_id IS NULL) AS parser_logs_unmapped;
