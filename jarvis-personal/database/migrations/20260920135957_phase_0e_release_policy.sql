BEGIN;

CREATE TABLE IF NOT EXISTS public.app_release_policies (
  platform TEXT PRIMARY KEY CHECK (platform IN ('android', 'ios', 'web')),
  minimum_supported_version TEXT NOT NULL CHECK (minimum_supported_version ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9.-]+)?$'),
  latest_version TEXT NOT NULL CHECK (latest_version ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9.-]+)?$'),
  update_url TEXT CHECK (update_url IS NULL OR update_url ~ '^https://'),
  message_es TEXT NOT NULL DEFAULT 'Hay una nueva versión de FINVA disponible.',
  message_en TEXT NOT NULL DEFAULT 'A new FINVA version is available.',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  updated_by_account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.app_release_policies (
  platform, minimum_supported_version, latest_version, update_url,
  message_es, message_en, is_active
) VALUES
  ('android', '1.0.0', '1.0.0', NULL,
   'Hay una nueva versión de FINVA disponible.',
   'A new FINVA version is available.', TRUE),
  ('ios', '1.0.0', '1.0.0', NULL,
   'Hay una nueva versión de FINVA disponible.',
   'A new FINVA version is available.', FALSE),
  ('web', '1.0.0', '1.0.0', NULL,
   'Hay una nueva versión de FINVA disponible.',
   'A new FINVA version is available.', FALSE)
ON CONFLICT (platform) DO NOTHING;

ALTER TABLE public.app_release_policies ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.app_release_policies FROM anon, authenticated;

COMMENT ON TABLE public.app_release_policies IS
  'Backend-only FINVA release compatibility policy. Never read directly from the Data API.';

COMMIT;
