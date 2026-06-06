-- Fase 7 — Notificaciones reales Web Push / PWA
-- Ejecutar en Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS notification_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL DEFAULT 'browser',
    endpoint TEXT,
    payload JSONB,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_success_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, channel, endpoint)
);

ALTER TABLE notification_subscriptions ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ;
ALTER TABLE notification_subscriptions ADD COLUMN IF NOT EXISTS last_error TEXT;

CREATE TABLE IF NOT EXISTS notification_jobs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reference_type TEXT,
    reference_id TEXT,
    dedupe_key TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    sent_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_notification_jobs_due ON notification_jobs(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_notification_jobs_user ON notification_jobs(user_id, scheduled_at);

-- Ejemplo opcional para prueba manual. Cambiá scheduled_at si querés probar cron.
-- INSERT INTO notification_jobs (user_id, title, body, category, scheduled_at, dedupe_key)
-- SELECT id, 'J.A.R.V.I.S.', 'Señor Kenneth, prueba programada de notificaciones.', 'test', NOW() + INTERVAL '1 minute', 'manual:test:phase7'
-- FROM allowed_users WHERE email = 'gatotico99@gmail.com'
-- ON CONFLICT (user_id, dedupe_key) DO NOTHING;
