-- Fase Email Parser Real
-- - Corrige query Gmail financiera.
-- - Mantiene autoguardado apagado.
-- - Siembra alias de tarjetas conocidos.
-- - Limpia artefactos pendientes para reanalizar con el parser nuevo.

WITH owner_user AS (
    SELECT id
    FROM users
    WHERE email = 'gatotico99@gmail.com'
    LIMIT 1
)
UPDATE email_monitor_settings
SET gmail_query = '(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr OR from:estadosdecuenta@baccredomatic.cr OR from:estadodecuenta@baccredomatic.cr OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com OR from:bancopopular OR from:popular OR "BAC - SINPE" OR "Banco Popular") ("Notificación de transacción" OR "Notificación de Transferencia" OR "Transacción realizada" OR "Estado de cuenta" OR "Estado de Cuenta" OR "estados de cuenta" OR SINPE OR transferencia OR compra OR pago OR depósito OR deposito OR retiro OR abono)',
    auto_commit_confidence = 999,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM owner_user);

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
CREATE INDEX IF NOT EXISTS idx_card_aliases_user ON card_aliases(user_id);

INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT id, '3131', 'Kenneth', 'principal', TRUE
FROM users
WHERE email = 'gatotico99@gmail.com'
ON CONFLICT (user_id, card_last4)
DO UPDATE SET owner_label = EXCLUDED.owner_label,
              relationship = EXCLUDED.relationship,
              is_primary = EXCLUDED.is_primary,
              updated_at = NOW();

INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT id, '2205', 'Emily', 'hermana / tarjeta adicional', FALSE
FROM users
WHERE email = 'gatotico99@gmail.com'
ON CONFLICT (user_id, card_last4)
DO UPDATE SET owner_label = EXCLUDED.owner_label,
              relationship = EXCLUDED.relationship,
              is_primary = EXCLUDED.is_primary,
              updated_at = NOW();

-- Borra SOLO pendientes del monitor para que el nuevo parser pueda reanalizar limpio.
DELETE FROM email_transaction_candidates
WHERE user_id = (SELECT id FROM users WHERE email = 'gatotico99@gmail.com' LIMIT 1)
  AND source = 'email_monitor'
  AND transaction_id IS NULL
  AND status IN ('pending','duplicate','rejected')
  AND created_at >= NOW() - INTERVAL '90 days';

DELETE FROM email_ingested_messages
WHERE user_id = (SELECT id FROM users WHERE email = 'gatotico99@gmail.com' LIMIT 1)
  AND provider = 'gmail'
  AND created_at >= NOW() - INTERVAL '90 days'
  AND NOT EXISTS (
      SELECT 1
      FROM email_transaction_candidates c
      WHERE c.email_message_id = email_ingested_messages.id
        AND c.transaction_id IS NOT NULL
  );
