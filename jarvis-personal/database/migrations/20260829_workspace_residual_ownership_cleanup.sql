BEGIN;

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['ai_usage_daily','ai_usage_events','ai_premium_usage_events','ai_premium_guides','ai_premium_settings','notification_jobs'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS workspace_id UUID', t);
      EXECUTE format($q$UPDATE %I x SET workspace_id=(SELECT w.id FROM accounts a JOIN workspaces w ON w.owner_account_id=a.id AND w.workspace_type='personal' WHERE a.legacy_allowed_user_id=x.user_id ORDER BY w.created_at,w.id LIMIT 1) WHERE x.workspace_id IS NULL$q$, t);
    END IF;
  END LOOP;
END $$;

DO $$
DECLARE t TEXT; n BIGINT;
BEGIN
  FOREACH t IN ARRAY ARRAY['ai_usage_daily','ai_usage_events','ai_premium_usage_events','ai_premium_guides','ai_premium_settings','notification_jobs'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('SELECT COUNT(*) FROM %I WHERE workspace_id IS NULL',t) INTO n;
      IF n>0 THEN RAISE EXCEPTION '% has % unmapped workspace rows',t,n; END IF;
      EXECUTE format('ALTER TABLE %I ALTER COLUMN workspace_id SET NOT NULL',t);
    END IF;
  END LOOP;
END $$;

DO $$ BEGIN
 IF to_regclass('public.ai_usage_daily') IS NOT NULL THEN CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_usage_daily_workspace_date ON ai_usage_daily(workspace_id,usage_date); END IF;
 IF to_regclass('public.ai_premium_settings') IS NOT NULL THEN CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_premium_settings_workspace ON ai_premium_settings(workspace_id); END IF;
 IF to_regclass('public.notification_jobs') IS NOT NULL THEN CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_jobs_workspace_dedupe ON notification_jobs(workspace_id,dedupe_key) WHERE dedupe_key IS NOT NULL; END IF;
 IF to_regclass('public.notification_subscriptions') IS NOT NULL THEN CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_subscriptions_workspace_channel_endpoint ON notification_subscriptions(workspace_id,channel,endpoint) WHERE endpoint IS NOT NULL; END IF;
END $$;

COMMIT;

CREATE TEMP TABLE _workspace_residual_audit (table_name TEXT PRIMARY KEY, unmapped BIGINT);
DO $$
DECLARE t TEXT; n BIGINT;
BEGIN
  FOREACH t IN ARRAY ARRAY['ai_usage_daily','ai_usage_events','ai_premium_usage_events','ai_premium_guides','ai_premium_settings','notification_jobs'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('SELECT COUNT(*) FROM %I WHERE workspace_id IS NULL',t) INTO n;
    ELSE
      n := 0;
    END IF;
    INSERT INTO _workspace_residual_audit(table_name,unmapped) VALUES(t,n);
  END LOOP;
END $$;

SELECT
 COALESCE((SELECT unmapped FROM _workspace_residual_audit WHERE table_name='ai_usage_daily'),0) AS ai_usage_daily_unmapped,
 COALESCE((SELECT unmapped FROM _workspace_residual_audit WHERE table_name='ai_usage_events'),0) AS ai_usage_events_unmapped,
 COALESCE((SELECT unmapped FROM _workspace_residual_audit WHERE table_name='ai_premium_usage_events'),0) AS premium_usage_unmapped,
 COALESCE((SELECT unmapped FROM _workspace_residual_audit WHERE table_name='ai_premium_guides'),0) AS premium_guides_unmapped,
 COALESCE((SELECT unmapped FROM _workspace_residual_audit WHERE table_name='ai_premium_settings'),0) AS premium_settings_unmapped,
 COALESCE((SELECT unmapped FROM _workspace_residual_audit WHERE table_name='notification_jobs'),0) AS notification_jobs_unmapped;
