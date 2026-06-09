BEGIN;

-- Correct the card/alias catalog so additional cards only include Emily and Sidey.
UPDATE card_aliases
SET owner_label = 'Kenneth',
    relationship = 'principal',
    is_primary = TRUE,
    updated_at = NOW()
WHERE user_id = 1
  AND card_last4 IN ('8137', '8295');

DELETE FROM card_aliases
WHERE user_id = 1
  AND card_last4 = 'PEND';

INSERT INTO card_aliases (user_id, card_last4, owner_label, relationship, is_primary, created_at, updated_at)
VALUES
  (1, '1655', 'Kenneth', 'principal', TRUE, NOW(), NOW()),
  (1, '7514', 'Kenneth', 'principal', TRUE, NOW(), NOW()),
  (1, '2179', 'Sidey', 'adicional', FALSE, NOW(), NOW())
ON CONFLICT (user_id, card_last4)
DO UPDATE SET
  owner_label = EXCLUDED.owner_label,
  relationship = EXCLUDED.relationship,
  is_primary = EXCLUDED.is_primary,
  updated_at = NOW();

UPDATE email_transaction_candidates
SET card_owner = 'Kenneth',
    updated_at = NOW()
WHERE user_id = 1
  AND card_last4 IN ('8137', '8295');

COMMIT;
