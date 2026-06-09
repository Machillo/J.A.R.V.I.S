-- J.A.R.V.I.S. Email Parser Fase 1.5
-- Normalización de comercios, propietarios de tarjeta y deduplicación semántica.
-- Ejecutar en Supabase SQL Editor antes de re-procesar los 67 candidates.

BEGIN;

ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS canonical_transaction_id BIGINT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS transaction_time TIME;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS raw_description TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS normalized_description TEXT;

CREATE INDEX IF NOT EXISTS idx_email_candidates_semantic_dedupe
ON email_transaction_candidates(user_id, transaction_date, amount, transaction_time, status);

CREATE INDEX IF NOT EXISTS idx_email_candidates_canonical
ON email_transaction_candidates(user_id, canonical_transaction_id);

-- Catálogo base de tarjetas detectadas en producción. Las tarjetas nuevas quedan
-- como PENDIENTE hasta que se confirme dueño; el backfill posterior actualiza
-- automáticamente si el parser ya pudo leer el saludo del correo.
INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary)
SELECT u.id, v.card_last4, v.owner_label, v.relationship, v.is_primary
FROM users u
CROSS JOIN (VALUES
    ('3131', 'Kenneth', 'principal', TRUE),
    ('2205', 'Emily', 'familiar', FALSE),
    ('PEND', 'Sidey', 'pendiente', FALSE),
    ('3149', 'PENDIENTE', 'pendiente_confirmacion', FALSE),
    ('5108', 'PENDIENTE', 'pendiente_confirmacion', FALSE),
    ('8295', 'PENDIENTE', 'pendiente_confirmacion', FALSE),
    ('8137', 'PENDIENTE', 'pendiente_confirmacion', FALSE)
) AS v(card_last4, owner_label, relationship, is_primary)
WHERE u.email = 'gatotico99@gmail.com'
ON CONFLICT (user_id, card_last4)
DO UPDATE SET
    owner_label = CASE
        WHEN card_aliases.owner_label IS NULL
          OR card_aliases.owner_label = ''
          OR card_aliases.owner_label = 'PENDIENTE'
        THEN EXCLUDED.owner_label
        ELSE card_aliases.owner_label
    END,
    relationship = COALESCE(card_aliases.relationship, EXCLUDED.relationship),
    is_primary = card_aliases.is_primary OR EXCLUDED.is_primary,
    updated_at = NOW();

-- Backfill owner desde alias confirmado.
UPDATE email_transaction_candidates c
SET card_owner = a.owner_label,
    updated_at = NOW()
FROM card_aliases a
WHERE c.user_id = a.user_id
  AND c.card_last4 = a.card_last4
  AND COALESCE(NULLIF(a.owner_label, ''), 'PENDIENTE') <> 'PENDIENTE'
  AND (c.card_owner IS NULL OR c.card_owner = '' OR c.card_owner = 'PENDIENTE');

-- Backfill owner directo desde saludo del correo para históricos.
UPDATE email_transaction_candidates c
SET card_owner = CASE
        WHEN LOWER(COALESCE(m.body_text, m.raw_body, m.raw_excerpt, '')) LIKE '%hola kenneth%' THEN 'Kenneth'
        WHEN LOWER(COALESCE(m.body_text, m.raw_body, m.raw_excerpt, '')) LIKE '%hola emily%' THEN 'Emily'
        WHEN LOWER(COALESCE(m.body_text, m.raw_body, m.raw_excerpt, '')) LIKE '%hola sidey%' THEN 'Sidey'
        ELSE c.card_owner
    END,
    updated_at = NOW()
FROM email_ingested_messages m
WHERE c.email_message_id = m.id
  AND (c.card_owner IS NULL OR c.card_owner = '' OR c.card_owner = 'PENDIENTE')
  AND (
      LOWER(COALESCE(m.body_text, m.raw_body, m.raw_excerpt, '')) LIKE '%hola kenneth%'
      OR LOWER(COALESCE(m.body_text, m.raw_body, m.raw_excerpt, '')) LIKE '%hola emily%'
      OR LOWER(COALESCE(m.body_text, m.raw_body, m.raw_excerpt, '')) LIKE '%hola sidey%'
  );

-- Si un card_last4 nuevo ya tiene movimientos con owner leído del correo,
-- promocionarlo automáticamente al catálogo de alias.
UPDATE card_aliases a
SET owner_label = inferred.owner_label,
    relationship = COALESCE(NULLIF(a.relationship, 'pendiente_confirmacion'), 'auto_inferido_email'),
    updated_at = NOW()
FROM (
    SELECT user_id, card_last4, MIN(card_owner) AS owner_label
    FROM email_transaction_candidates
    WHERE card_last4 IS NOT NULL
      AND card_owner IS NOT NULL
      AND card_owner <> ''
      AND card_owner <> 'PENDIENTE'
    GROUP BY user_id, card_last4
) inferred
WHERE a.user_id = inferred.user_id
  AND a.card_last4 = inferred.card_last4
  AND (a.owner_label IS NULL OR a.owner_label = '' OR a.owner_label = 'PENDIENTE');

-- Backfill simple de normalización para históricos. El código Python hará la
-- normalización completa; este bloque cubre los casos reales ya observados.
UPDATE email_transaction_candidates
SET raw_description = COALESCE(raw_description, description),
    normalized_description = CASE
        WHEN UPPER(description) LIKE '%APPLE.COM%BILL%' THEN 'APPLE'
        WHEN UPPER(description) LIKE '%OPENAI%' OR UPPER(description) LIKE '%CHATGPT%' THEN 'OPENAI'
        WHEN UPPER(description) LIKE '%BARBER SHOP%' THEN 'BARBER SHOP'
        ELSE UPPER(REGEXP_REPLACE(description, '\s+', ' ', 'g'))
    END,
    description = CASE
        WHEN UPPER(description) LIKE '%APPLE.COM%BILL%' THEN 'APPLE'
        WHEN UPPER(description) LIKE '%OPENAI%' OR UPPER(description) LIKE '%CHATGPT%' THEN 'OPENAI'
        WHEN UPPER(description) LIKE '%BARBER SHOP%' THEN 'BARBER SHOP'
        ELSE UPPER(REGEXP_REPLACE(description, '\s+', ' ', 'g'))
    END,
    updated_at = NOW()
WHERE raw_description IS NULL OR normalized_description IS NULL;

-- Inicializar canonical_transaction_id para registros pendientes/confirmados.
UPDATE email_transaction_candidates
SET canonical_transaction_id = id,
    updated_at = NOW()
WHERE canonical_transaction_id IS NULL
  AND status IN ('pending', 'confirmed', 'auto_saved');

-- Conciliar duplicados semánticos históricos: mismo monto, misma fecha y hora ±10 min.
WITH scored AS (
    SELECT
        c.*,
        CASE
            WHEN UPPER(c.description) LIKE '%INVERSION VISTA SMART%' THEN 10
            WHEN UPPER(c.description) LIKE '%DEBITO APLICADO POR OTRA ENTIDAD%' THEN 10
            WHEN UPPER(c.description) LIKE '%MOVIMIENTO MULTIMONEY%' THEN 10
            WHEN UPPER(c.description) LIKE '%SINPE%' THEN 70
            ELSE 80
        END AS canonical_score
    FROM email_transaction_candidates c
    WHERE c.status IN ('pending','confirmed','auto_saved')
), pairs AS (
    SELECT
        a.id AS candidate_id,
        FIRST_VALUE(b.id) OVER (
            PARTITION BY a.id
            ORDER BY b.canonical_score DESC, b.created_at ASC, b.id ASC
        ) AS canonical_id
    FROM scored a
    JOIN scored b
      ON a.user_id = b.user_id
     AND a.id <> b.id
     AND a.transaction_date = b.transaction_date
     AND ABS(a.amount - b.amount) < 0.01
     AND (
        a.transaction_time IS NULL
        OR b.transaction_time IS NULL
        OR ABS(EXTRACT(EPOCH FROM ((a.transaction_date + a.transaction_time) - (b.transaction_date + b.transaction_time)))) <= 600
     )
)
UPDATE email_transaction_candidates c
SET status = CASE WHEN c.id = p.canonical_id THEN c.status ELSE 'duplicate' END,
    duplicate_of = CASE WHEN c.id = p.canonical_id THEN NULL ELSE p.canonical_id END,
    canonical_transaction_id = p.canonical_id,
    review_reason = CASE
        WHEN c.id = p.canonical_id THEN c.review_reason
        ELSE 'Duplicado semántico histórico: mismo monto, fecha y ventana de ±10 minutos.'
    END,
    updated_at = NOW()
FROM pairs p
WHERE c.id = p.candidate_id
  AND c.id <> p.canonical_id;

COMMIT;
