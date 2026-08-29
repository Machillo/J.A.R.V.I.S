-- Phase 4C: workspace ownership for remaining request-scoped Personal services.
-- Non-destructive: legacy user_id remains during compatibility period.

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['logs','chat_sessions','chat_pending_actions','memory_items','user_preferences','notification_subscriptions'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE', t);
      EXECUTE format('UPDATE %I x SET workspace_id = w.id FROM accounts a JOIN workspaces w ON w.owner_account_id=a.id AND w.workspace_type=''personal'' WHERE x.workspace_id IS NULL AND a.legacy_allowed_user_id=x.user_id', t);
      EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(workspace_id)', 'idx_'||t||'_workspace_id', t);
    END IF;
  END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_preferences_workspace_key
ON user_preferences(workspace_id, preference_key);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_subscriptions_workspace_endpoint
ON notification_subscriptions(workspace_id, channel, endpoint);

SELECT
  (SELECT COUNT(*) FROM logs WHERE workspace_id IS NULL) AS logs_unmapped,
  (SELECT COUNT(*) FROM chat_sessions WHERE workspace_id IS NULL) AS chat_sessions_unmapped,
  (SELECT COUNT(*) FROM chat_pending_actions WHERE workspace_id IS NULL) AS chat_actions_unmapped,
  (SELECT COUNT(*) FROM memory_items WHERE workspace_id IS NULL) AS memory_unmapped,
  (SELECT COUNT(*) FROM user_preferences WHERE workspace_id IS NULL) AS preferences_unmapped,
  (SELECT COUNT(*) FROM notification_subscriptions WHERE workspace_id IS NULL) AS subscriptions_unmapped;
