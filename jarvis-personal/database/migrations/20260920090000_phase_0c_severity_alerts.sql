BEGIN;

ALTER TABLE public.feedback_reports
  ADD COLUMN IF NOT EXISTS discord_alerted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_feedback_unalerted_critical
  ON public.feedback_reports(last_seen_at DESC)
  WHERE source = 'automatic' AND severity = 'critical' AND discord_alerted_at IS NULL;

ALTER TABLE public.feedback_reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.feedback_reports FROM anon, authenticated;

COMMIT;
