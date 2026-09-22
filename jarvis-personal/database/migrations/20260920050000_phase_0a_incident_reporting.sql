BEGIN;

ALTER TABLE public.feedback_reports
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'user',
  ADD COLUMN IF NOT EXISTS severity TEXT NOT NULL DEFAULT 'info',
  ADD COLUMN IF NOT EXISTS fingerprint TEXT,
  ADD COLUMN IF NOT EXISTS request_id TEXT,
  ADD COLUMN IF NOT EXISTS error_reference TEXT,
  ADD COLUMN IF NOT EXISTS screen TEXT,
  ADD COLUMN IF NOT EXISTS platform TEXT,
  ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS occurrence_count INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS user_resolution TEXT,
  ADD COLUMN IF NOT EXISTS user_resolution_at TIMESTAMPTZ;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'feedback_reports_source_check') THEN
    ALTER TABLE public.feedback_reports ADD CONSTRAINT feedback_reports_source_check
      CHECK (source IN ('user', 'automatic')) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'feedback_reports_severity_check') THEN
    ALTER TABLE public.feedback_reports ADD CONSTRAINT feedback_reports_severity_check
      CHECK (severity IN ('info', 'warning', 'critical')) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'feedback_reports_occurrence_count_check') THEN
    ALTER TABLE public.feedback_reports ADD CONSTRAINT feedback_reports_occurrence_count_check
      CHECK (occurrence_count >= 1) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'feedback_reports_user_resolution_check') THEN
    ALTER TABLE public.feedback_reports ADD CONSTRAINT feedback_reports_user_resolution_check
      CHECK (user_resolution IS NULL OR user_resolution IN ('resolved', 'still_happening')) NOT VALID;
  END IF;
END $$;

ALTER TABLE public.feedback_reports VALIDATE CONSTRAINT feedback_reports_source_check;
ALTER TABLE public.feedback_reports VALIDATE CONSTRAINT feedback_reports_severity_check;
ALTER TABLE public.feedback_reports VALIDATE CONSTRAINT feedback_reports_occurrence_count_check;
ALTER TABLE public.feedback_reports VALIDATE CONSTRAINT feedback_reports_user_resolution_check;

CREATE INDEX IF NOT EXISTS idx_feedback_incident_dedupe
  ON public.feedback_reports(account_id, fingerprint, last_seen_at DESC)
  WHERE fingerprint IS NOT NULL;

ALTER TABLE public.feedback_reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.feedback_reports FROM anon, authenticated;

COMMIT;
