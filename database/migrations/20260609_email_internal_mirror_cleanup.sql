BEGIN;

-- BAC sometimes shows the same BAC account as N°****1813 while the IBAN ends
-- in 8137. Both identify Kenneth's own money route and must not appear as
-- additional-card spending.
DELETE FROM card_aliases
WHERE user_id = 1 AND card_last4 IN ('1813');

INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary, created_at, updated_at)
VALUES (1, '1813', 'Kenneth', 'principal', TRUE, NOW(), NOW());

-- Keep already-known own routes sane. These are not Sidey/Emily additional cards.
UPDATE card_aliases
SET owner_label = 'Kenneth', relationship = 'principal', is_primary = TRUE, updated_at = NOW()
WHERE user_id = 1 AND card_last4 IN ('3131', '5108', '1655', '7514', '8137', '8295', '1813');

UPDATE card_aliases
SET owner_label = 'Emily', relationship = 'adicional', is_primary = FALSE, updated_at = NOW()
WHERE user_id = 1 AND card_last4 IN ('2205', '3149');

UPDATE card_aliases
SET owner_label = 'Sidey', relationship = 'adicional', is_primary = FALSE, updated_at = NOW()
WHERE user_id = 1 AND card_last4 = '2179';

-- If a previous scan created candidates for known internal movement concepts,
-- remove them from the review queue. The current conversation already cleaned
-- candidates to zero, but this keeps deploys safe if another environment has rows.
DELETE FROM email_transaction_candidates
WHERE user_id = 1
  AND status = 'pending'
  AND transaction_id IS NULL
  AND (
    transaction_type = 'internal_transfer'
    OR COALESCE(raw_description, description, '') ILIKE '%INVERSION VISTA SMART%'
    OR COALESCE(raw_description, description, '') ILIKE '%INVERSIÓN VISTA SMART%'
    OR COALESCE(raw_description, description, '') ILIKE '%DEBITO APLICADO POR OTRA ENTIDAD FINANCIERA%'
    OR COALESCE(raw_description, description, '') ILIKE '%DÉBITO APLICADO POR OTRA ENTIDAD FINANCIERA%'
    OR COALESCE(notes, '') ILIKE '%cuentas propias%'
    OR COALESCE(notes, '') ILIKE '%Movimiento interno%'
  );

COMMIT;
