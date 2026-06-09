-- Fase Email Parser Real 1.5
-- Corte BAC 21 -> 21, tarjetas adicionales, parser pagos BAC alerta y deduplicación.
-- Ejecutar antes de volver a escanear correos.

ALTER TABLE email_ingested_messages
    ADD COLUMN IF NOT EXISTS raw_body TEXT,
    ADD COLUMN IF NOT EXISTS body_text TEXT,
    ADD COLUMN IF NOT EXISTS attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS attachment_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS parse_reason TEXT;

ALTER TABLE email_transaction_candidates
    ADD COLUMN IF NOT EXISTS card_last4 TEXT,
    ADD COLUMN IF NOT EXISTS card_owner TEXT,
    ADD COLUMN IF NOT EXISTS billing_cycle_start DATE,
    ADD COLUMN IF NOT EXISTS billing_cycle_end DATE,
    ADD COLUMN IF NOT EXISTS dedupe_key TEXT,
    ADD COLUMN IF NOT EXISTS duplicate_of BIGINT;

CREATE INDEX IF NOT EXISTS idx_email_candidates_card_cycle
ON email_transaction_candidates(user_id, card_last4, billing_cycle_start, billing_cycle_end);

CREATE INDEX IF NOT EXISTS idx_email_candidates_dedupe
ON email_transaction_candidates(user_id, transaction_date, amount, transaction_type, status);

CREATE TABLE IF NOT EXISTS card_aliases (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    card_last4 TEXT NOT NULL,
    owner_label TEXT NOT NULL,
    relationship TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, card_last4)
);

-- Compatibilidad: en versiones anteriores esta tabla solo tenía
-- id, user_id, name, cut_day, payment_day, created_at.
-- Por eso NO podemos asumir que bank/card_last4 ya existen.
CREATE TABLE IF NOT EXISTS credit_card_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL DEFAULT 'BAC tarjetas',
    cut_day INTEGER NOT NULL DEFAULT 21,
    payment_day INTEGER NOT NULL DEFAULT 5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE credit_card_settings
    ADD COLUMN IF NOT EXISTS bank TEXT NOT NULL DEFAULT 'bac',
    ADD COLUMN IF NOT EXISTS card_last4 TEXT,
    ADD COLUMN IF NOT EXISTS owner_label TEXT,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_card_settings_user_bank_card
ON credit_card_settings(user_id, bank, card_last4);

CREATE TABLE IF NOT EXISTS email_parser_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    provider_message_id TEXT,
    sender TEXT,
    subject TEXT,
    bank TEXT,
    action TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Owner actual del proyecto.
WITH owner AS (
    SELECT id FROM users WHERE email = 'gatotico99@gmail.com' LIMIT 1
)
INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT id, '3131', 'Kenneth', 'owner', TRUE FROM owner
ON CONFLICT (user_id, card_last4) DO UPDATE SET
    owner_label = EXCLUDED.owner_label,
    relationship = EXCLUDED.relationship,
    is_primary = EXCLUDED.is_primary,
    updated_at = NOW();

WITH owner AS (
    SELECT id FROM users WHERE email = 'gatotico99@gmail.com' LIMIT 1
)
INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT id, '2205', 'Emily', 'hermana', FALSE FROM owner
ON CONFLICT (user_id, card_last4) DO UPDATE SET
    owner_label = EXCLUDED.owner_label,
    relationship = EXCLUDED.relationship,
    is_primary = EXCLUDED.is_primary,
    updated_at = NOW();

-- Si luego confirmás los últimos 4 de Sidey, agregalo igual en card_aliases.

WITH owner AS (
    SELECT id FROM users WHERE email = 'gatotico99@gmail.com' LIMIT 1
)
INSERT INTO credit_card_settings (user_id, name, bank, card_last4, owner_label, cut_day, payment_day, is_active, updated_at)
SELECT id, 'BAC Kenneth ****3131', 'bac', '3131', 'Kenneth', 21, 5, TRUE, NOW() FROM owner
ON CONFLICT (user_id, bank, card_last4) DO UPDATE SET
    name = EXCLUDED.name,
    owner_label = EXCLUDED.owner_label,
    cut_day = EXCLUDED.cut_day,
    payment_day = EXCLUDED.payment_day,
    is_active = TRUE,
    updated_at = NOW();

WITH owner AS (
    SELECT id FROM users WHERE email = 'gatotico99@gmail.com' LIMIT 1
)
INSERT INTO credit_card_settings (user_id, name, bank, card_last4, owner_label, cut_day, payment_day, is_active, updated_at)
SELECT id, 'BAC Emily ****2205', 'bac', '2205', 'Emily', 21, 5, TRUE, NOW() FROM owner
ON CONFLICT (user_id, bank, card_last4) DO UPDATE SET
    name = EXCLUDED.name,
    owner_label = EXCLUDED.owner_label,
    cut_day = EXCLUDED.cut_day,
    payment_day = EXCLUDED.payment_day,
    is_active = TRUE,
    updated_at = NOW();

-- Fuerza query amplia por remitente. El parser decide qué ignorar.
WITH owner AS (
    SELECT id FROM users WHERE email = 'gatotico99@gmail.com' LIMIT 1
)
UPDATE email_monitor_settings
SET gmail_query = '(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr OR from:alerta@baccredomatic.com OR from:estadosdecuenta@baccredomatic.cr OR from:estadodecuenta@baccredomatic.cr OR from:info@info.baccredomatic.net OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com OR from:bancopopular.fi.cr OR from:bancopopular OR from:popular)',
    auto_commit_confidence = 999,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM owner);
