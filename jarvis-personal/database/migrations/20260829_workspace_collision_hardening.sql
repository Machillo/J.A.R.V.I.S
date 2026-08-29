BEGIN;

-- Remove only legacy uniqueness/index boundaries whose business key is now workspace-owned.
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT c.conrelid::regclass AS tbl, c.conname
        FROM pg_constraint c
        WHERE c.contype = 'u'
          AND c.conrelid IN (
              to_regclass('public.exchange_rates'),
              to_regclass('public.user_preferences'),
              to_regclass('public.notification_subscriptions'),
              to_regclass('public.notification_jobs'),
              to_regclass('public.email_ingested_messages'),
              to_regclass('public.email_transaction_candidates'),
              to_regclass('public.email_statement_documents'),
              to_regclass('public.card_aliases')
          )
          AND (
              pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id, rate_date, currency\)'
           OR pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id, preference_key\)'
           OR pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id, channel, endpoint\)'
           OR pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id, dedupe_key\)'
           OR pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id, fingerprint\)'
           OR pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id, provider, provider_message_id\)'
           OR pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id, email_message_id\)'
           OR pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id, card_last4\)'
          )
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
    END LOOP;
END $$;

-- Legacy partial unique index used by automatic receivables.
DROP INDEX IF EXISTS uq_receivable_entries_source_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_exchange_rates_workspace_date_currency
    ON exchange_rates(workspace_id, rate_date, currency);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_preferences_workspace_key
    ON user_preferences(workspace_id, preference_key);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_subscriptions_workspace_channel_endpoint
    ON notification_subscriptions(workspace_id, channel, endpoint);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_jobs_workspace_dedupe
    ON notification_jobs(workspace_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_messages_workspace_fingerprint
    ON email_ingested_messages(workspace_id, fingerprint);

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_messages_workspace_provider_message
    ON email_ingested_messages(workspace_id, provider, provider_message_id)
    WHERE provider_message_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_candidates_workspace_fingerprint
    ON email_transaction_candidates(workspace_id, fingerprint);

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_statements_workspace_message
    ON email_statement_documents(workspace_id, email_message_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_card_aliases_workspace_last4
    ON card_aliases(workspace_id, card_last4);

CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_entries_source_key
    ON receivable_entries(workspace_id, source_key)
    WHERE source_key IS NOT NULL;

DROP INDEX IF EXISTS idx_receivables_source_key;
CREATE INDEX IF NOT EXISTS idx_receivables_source_key
    ON receivables(workspace_id, source_key);

COMMIT;

SELECT
    (
        SELECT COUNT(*)
        FROM pg_constraint c
        WHERE c.contype = 'u'
          AND c.conrelid IN (
              to_regclass('public.exchange_rates'),
              to_regclass('public.user_preferences'),
              to_regclass('public.notification_subscriptions'),
              to_regclass('public.notification_jobs'),
              to_regclass('public.email_ingested_messages'),
              to_regclass('public.email_transaction_candidates'),
              to_regclass('public.email_statement_documents'),
              to_regclass('public.card_aliases')
          )
          AND pg_get_constraintdef(c.oid) ~* 'UNIQUE \(user_id,'
    ) AS legacy_user_unique_constraints_remaining,
    (
        SELECT COUNT(*)
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexdef ~* 'UNIQUE'
          AND indexdef ~* '\(user_id, source_key\)'
    ) AS legacy_user_sourcekey_unique_indexes_remaining;
