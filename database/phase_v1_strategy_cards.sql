-- V1 - Estrategia premium ampliada + tarjetas adicionales.
-- Seguro para ejecutar varias veces.

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

INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT id, '3131', 'Kenneth', 'principal', TRUE
FROM users
WHERE email = 'gatotico99@gmail.com'
ON CONFLICT (user_id, card_last4)
DO UPDATE SET owner_label = EXCLUDED.owner_label, relationship = EXCLUDED.relationship, is_primary = EXCLUDED.is_primary, updated_at = NOW();

INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT id, '2205', 'Emily', 'hermana', FALSE
FROM users
WHERE email = 'gatotico99@gmail.com'
ON CONFLICT (user_id, card_last4)
DO UPDATE SET owner_label = EXCLUDED.owner_label, relationship = EXCLUDED.relationship, is_primary = EXCLUDED.is_primary, updated_at = NOW();

-- Sidey queda preparada; cuando tengas el último 4 de su tarjeta, actualizas card_last4.
INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT id, 'PEND', 'Sidey', 'mamá', FALSE
FROM users
WHERE email = 'gatotico99@gmail.com'
ON CONFLICT (user_id, card_last4)
DO UPDATE SET owner_label = EXCLUDED.owner_label, relationship = EXCLUDED.relationship, is_primary = EXCLUDED.is_primary, updated_at = NOW();

CREATE INDEX IF NOT EXISTS idx_card_aliases_user ON card_aliases(user_id);
