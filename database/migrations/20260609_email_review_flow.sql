-- Fase Correos 100%: revisión manual antes de finanzas + tarjetas adicionales limpias.
-- Ejecutar en Supabase SQL Editor antes de desplegar frontend/backend.

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

ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS card_last4 TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS card_owner TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS canonical_transaction_id BIGINT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS duplicate_of BIGINT;

CREATE INDEX IF NOT EXISTS idx_email_candidates_user_status_created
ON email_transaction_candidates(user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_candidates_transaction_id
ON email_transaction_candidates(user_id, transaction_id);

CREATE INDEX IF NOT EXISTS idx_email_messages_provider_message
ON email_ingested_messages(user_id, provider, provider_message_id);

WITH owner_user AS (
    SELECT id AS user_id
    FROM allowed_users
    WHERE email = 'gatotico99@gmail.com'
    LIMIT 1
), aliases(card_last4, owner_label, relationship, is_primary) AS (
    VALUES
        ('3131', 'Kenneth', 'principal', TRUE),
        ('5108', 'Kenneth', 'principal', TRUE),
        ('2205', 'Emily', 'adicional', FALSE),
        ('3149', 'Emily', 'adicional', FALSE),
        ('8137', 'Sidey', 'adicional', FALSE),
        ('8295', 'Sidey', 'adicional', FALSE),
        ('PEND', 'Sidey', 'adicional', FALSE)
)
INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT owner_user.user_id, aliases.card_last4, aliases.owner_label, aliases.relationship, aliases.is_primary
FROM owner_user CROSS JOIN aliases
ON CONFLICT (user_id, card_last4) DO UPDATE
SET owner_label = EXCLUDED.owner_label,
    relationship = EXCLUDED.relationship,
    is_primary = EXCLUDED.is_primary,
    updated_at = NOW();

-- Backfill: candidates already parsed from known additional cards must get the right owner.
UPDATE email_transaction_candidates c
SET card_owner = a.owner_label,
    updated_at = NOW()
FROM card_aliases a
WHERE c.user_id = a.user_id
  AND c.card_last4 = a.card_last4
  AND COALESCE(c.card_owner, '') <> a.owner_label;
