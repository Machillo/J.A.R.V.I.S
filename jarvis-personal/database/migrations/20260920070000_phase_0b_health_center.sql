BEGIN;

ALTER TABLE public.feedback_reports
  ADD COLUMN IF NOT EXISTS affected_operations TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

UPDATE public.feedback_reports
SET affected_operations = ARRAY['legacy incident']
WHERE source = 'automatic' AND affected_operations = ARRAY[]::TEXT[];

CREATE INDEX IF NOT EXISTS idx_feedback_health_window
  ON public.feedback_reports(source, status, last_seen_at DESC)
  WHERE source = 'automatic';

ALTER TABLE public.feedback_reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.feedback_reports FROM anon, authenticated;

COMMIT;
