BEGIN;

-- 1) Eliminar pagos automáticos falsos que fueron aplicados sin evidencia clara
--    de Emily/Sidey. En especial corrige el caso del ingreso ₡577.20 que se
--    asignó erróneamente como pago de Emily.
DELETE FROM receivable_payments rp
USING receivables r
WHERE rp.receivable_id = r.id
  AND r.source_type = 'additional_card_auto'
  AND (
        rp.amount <= 1000
        OR COALESCE(rp.notes, '') NOT ILIKE '%emily%'
           AND COALESCE(rp.notes, '') NOT ILIKE '%sidey%'
      );

-- 2) Recalcular cuentas por cobrar automáticas desde la misma fuente real que
--    Tarjetas adicionales: email_transaction_candidates confirmados.
WITH additional_totals AS (
    SELECT
        c.user_id,
        COALESCE(a.owner_label, c.card_owner) AS person_name,
        LOWER(TRIM(COALESCE(a.owner_label, c.card_owner))) AS owner_key,
        COALESCE(SUM(c.amount), 0)::numeric(14,2) AS original_amount,
        COUNT(*) AS movement_count,
        STRING_AGG(DISTINCT COALESCE(c.card_last4, ''), ',' ORDER BY COALESCE(c.card_last4, '')) AS cards
    FROM email_transaction_candidates c
    LEFT JOIN card_aliases a
      ON a.user_id = c.user_id
     AND a.card_last4 = c.card_last4
    WHERE c.transaction_type = 'expense'
      AND c.amount > 0
      AND c.status IN ('confirmed', 'auto_saved', 'imported')
      AND COALESCE(c.status, '') NOT IN ('duplicate', 'rejected')
      AND LOWER(TRIM(COALESCE(a.owner_label, c.card_owner, ''))) IN ('emily', 'sidey')
    GROUP BY c.user_id, COALESCE(a.owner_label, c.card_owner), LOWER(TRIM(COALESCE(a.owner_label, c.card_owner)))
), existing_payments AS (
    SELECT
        r.id AS receivable_id,
        COALESCE(SUM(rp.amount), 0)::numeric(14,2) AS paid_amount
    FROM receivables r
    LEFT JOIN receivable_payments rp ON rp.receivable_id = r.id
    WHERE r.source_type = 'additional_card_auto'
    GROUP BY r.id
), upserted AS (
    UPDATE receivables r
    SET
        person_name = t.person_name,
        original_amount = t.original_amount,
        paid_amount = COALESCE(p.paid_amount, 0),
        pending_amount = GREATEST(t.original_amount - COALESCE(p.paid_amount, 0), 0),
        status = CASE
            WHEN GREATEST(t.original_amount - COALESCE(p.paid_amount, 0), 0) <= 0.01 THEN 'completed'
            WHEN COALESCE(p.paid_amount, 0) > 0 THEN 'partial'
            ELSE 'pending'
        END,
        notes = CONCAT('AUTO_ADDITIONAL_CARD owner=', t.person_name, '; cards=', COALESCE(t.cards, ''), '; movements=', t.movement_count),
        source_type = 'additional_card_auto',
        source_key = 'additional_cards:' || t.owner_key,
        updated_at = NOW()
    FROM additional_totals t
    LEFT JOIN existing_payments p ON p.receivable_id = r.id
    WHERE r.user_id = t.user_id
      AND r.source_key = 'additional_cards:' || t.owner_key
    RETURNING r.user_id, r.source_key
)
INSERT INTO receivables (
    user_id, person_name, original_amount, paid_amount, pending_amount,
    status, notes, source_type, source_key, created_at, updated_at
)
SELECT
    t.user_id,
    t.person_name,
    t.original_amount,
    0,
    t.original_amount,
    CASE WHEN t.original_amount <= 0.01 THEN 'completed' ELSE 'pending' END,
    CONCAT('AUTO_ADDITIONAL_CARD owner=', t.person_name, '; cards=', COALESCE(t.cards, ''), '; movements=', t.movement_count),
    'additional_card_auto',
    'additional_cards:' || t.owner_key,
    NOW(),
    NOW()
FROM additional_totals t
WHERE NOT EXISTS (
    SELECT 1
    FROM receivables r
    WHERE r.user_id = t.user_id
      AND r.source_key = 'additional_cards:' || t.owner_key
);

-- 3) Seguridad: cualquier auto-receivable de Emily/Sidey creado vacío por bugs
--    anteriores debe quedar pendiente si existe gasto confirmado.
UPDATE receivables
SET updated_at = NOW()
WHERE source_type = 'additional_card_auto';

COMMIT;
