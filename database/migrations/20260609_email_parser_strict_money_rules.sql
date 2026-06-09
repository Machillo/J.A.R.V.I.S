BEGIN;

-- Catálogo saneado: adicionales reales = Emily (2205, 3149) y Sidey (2179).
-- Kenneth incluye tarjetas propias, débito y cuentas usadas para detectar movimientos internos.
UPDATE card_aliases
SET owner_label = 'Kenneth', relationship = 'principal', is_primary = TRUE, updated_at = NOW()
WHERE user_id = 1 AND card_last4 IN ('3131', '5108', '1655', '7514', '8137', '8295');

UPDATE card_aliases
SET owner_label = 'Emily', relationship = 'adicional', is_primary = FALSE, updated_at = NOW()
WHERE user_id = 1 AND card_last4 IN ('2205', '3149');

DELETE FROM card_aliases
WHERE user_id = 1 AND card_last4 IN ('2179', '1655', '7514', 'PEND');

INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary, created_at, updated_at)
VALUES
  (1, '2179', 'Sidey', 'adicional', FALSE, NOW(), NOW()),
  (1, '1655', 'Kenneth', 'principal', TRUE, NOW(), NOW()),
  (1, '7514', 'Kenneth', 'principal', TRUE, NOW(), NOW());

UPDATE email_transaction_candidates
SET card_owner = 'Kenneth', updated_at = NOW()
WHERE user_id = 1 AND card_last4 IN ('8137', '8295', '1655', '7514');

-- Si algún re-proceso viejo dejó pagos de tarjeta o internos como candidatos,
-- que no se queden pendientes para finanzas.
UPDATE email_transaction_candidates
SET status = 'rejected',
    review_reason = COALESCE(NULLIF(review_reason, ''), 'Descartado: pago de tarjeta o movimiento interno; evita doble conteo.'),
    updated_at = NOW()
WHERE user_id = 1
  AND status IN ('pending', 'duplicate')
  AND (
    transaction_type = 'internal_transfer'
    OR normalized_description ILIKE '%VISTA SMART%'
    OR raw_description ILIKE '%VISTA SMART%'
    OR description ILIKE '%PAGO TARJETA BAC%'
    OR description ILIKE '%PAGO DE TARJETA%'
  );

COMMIT;
