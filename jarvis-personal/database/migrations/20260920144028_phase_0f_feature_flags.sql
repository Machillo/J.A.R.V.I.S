BEGIN;

CREATE TABLE IF NOT EXISTS public.app_feature_flags (
  flag_key TEXT PRIMARY KEY CHECK (flag_key ~ '^[a-z][a-z0-9_]{2,59}$'),
  display_name TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 3 AND 80),
  description TEXT NOT NULL CHECK (char_length(description) BETWEEN 3 AND 300),
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  safe_default_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  disabled_message_es TEXT NOT NULL CHECK (char_length(disabled_message_es) BETWEEN 3 AND 300),
  disabled_message_en TEXT NOT NULL CHECK (char_length(disabled_message_en) BETWEEN 3 AND 300),
  updated_by_account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_feature_flags_updated_by
  ON public.app_feature_flags(updated_by_account_id)
  WHERE updated_by_account_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.app_feature_flag_audit (
  id BIGSERIAL PRIMARY KEY,
  flag_key TEXT NOT NULL REFERENCES public.app_feature_flags(flag_key) ON DELETE RESTRICT,
  previous_enabled BOOLEAN NOT NULL,
  new_enabled BOOLEAN NOT NULL,
  reason TEXT NOT NULL CHECK (char_length(reason) BETWEEN 3 AND 300),
  changed_by_account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_feature_flag_audit_flag_changed
  ON public.app_feature_flag_audit(flag_key, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_feature_flag_audit_changed_by
  ON public.app_feature_flag_audit(changed_by_account_id)
  WHERE changed_by_account_id IS NOT NULL;

INSERT INTO public.app_feature_flags(
  flag_key,display_name,description,enabled,safe_default_enabled,
  disabled_message_es,disabled_message_en
) VALUES
  ('financial_writes','Escrituras financieras','Crear o modificar movimientos, deudas, metas y situación financiera.',TRUE,FALSE,
   'Los cambios financieros están pausados temporalmente. Tus datos guardados siguen disponibles.',
   'Financial changes are temporarily paused. Your saved data remains available.'),
  ('gmail_automation','Automatización Gmail','Conexión, sincronización e importación de movimientos desde Gmail.',TRUE,FALSE,
   'La automatización de Gmail está en mantenimiento temporal.',
   'Gmail automation is temporarily under maintenance.'),
  ('vip_intelligence','Inteligencia VIP','Dirección financiera, proyecciones y escenarios del plan VIP.',TRUE,TRUE,
   'La inteligencia VIP está en mantenimiento temporal.',
   'VIP intelligence is temporarily under maintenance.'),
  ('advanced_reports','Reportes avanzados','Reportes mensuales, anuales y análisis avanzados.',TRUE,TRUE,
   'Los reportes avanzados están en mantenimiento temporal.',
   'Advanced reports are temporarily under maintenance.'),
  ('store_billing','Billing de tienda','Catálogo, compras y restauración de suscripciones móviles.',TRUE,FALSE,
   'Las compras y restauraciones están pausadas temporalmente.',
   'Purchases and restores are temporarily paused.')
ON CONFLICT (flag_key) DO NOTHING;

ALTER TABLE public.app_feature_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_feature_flag_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.app_feature_flags FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.app_feature_flag_audit FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.app_feature_flag_audit_id_seq FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.app_feature_flags IS
  'Backend-only operational kill switches. Plan entitlements remain in plan_features.';
COMMENT ON TABLE public.app_feature_flag_audit IS
  'Immutable owner change log for operational kill switches.';

COMMIT;
