-- Fix automatic receivables source and keep Premium strategy aligned with real tables.
-- Safe to run multiple times.

BEGIN;

CREATE TABLE IF NOT EXISTS receivables (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    person_name TEXT NOT NULL,
    original_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    paid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    pending_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS receivable_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL,
    source_transaction_id BIGINT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Rebuild automatic additional-card receivables from the same metadata used by the UI.
WITH additional_aliases AS (
    SELECT user_id, card_last4, owner_label
    FROM card_aliases
    WHERE COALESCE(is_primary, FALSE) = FALSE
      AND LOWER(TRIM(owner_label)) NOT IN ('kenneth', 'kenneth andres')
), totals AS (
    SELECT
        c.user_id,
        COALESCE(a.owner_label, c.card_owner) AS person_name,
        LOWER(TRIM(COALESCE(a.owner_label, c.card_owner))) AS person_key,
        COALESCE(SUM(c.amount), 0)::NUMERIC(14,2) AS total_amount,
        COUNT(DISTINCT COALESCE(c.transaction_id, c.id * -1)) AS movement_count,
        ARRAY_AGG(DISTINCT COALESCE(a.card_last4, c.card_last4) ORDER BY COALESCE(a.card_last4, c.card_last4))
            FILTER (WHERE COALESCE(a.card_last4, c.card_last4) IS NOT NULL AND COALESCE(a.card_last4, c.card_last4) <> '') AS cards
    FROM email_transaction_candidates c
    LEFT JOIN additional_aliases a
      ON a.user_id = c.user_id
     AND a.card_last4 = c.card_last4
    WHERE c.transaction_type = 'expense'
      AND COALESCE(c.amount, 0) > 0
      AND COALESCE(c.status, '') IN ('confirmed', 'auto_saved', 'imported')
      AND COALESCE(c.status, '') NOT IN ('duplicate', 'rejected')
      AND (
            a.card_last4 IS NOT NULL
         OR LOWER(TRIM(COALESCE(c.card_owner,''))) IN (
                SELECT LOWER(TRIM(owner_label)) FROM additional_aliases WHERE user_id = c.user_id
            )
      )
    GROUP BY c.user_id, COALESCE(a.owner_label, c.card_owner), LOWER(TRIM(COALESCE(a.owner_label, c.card_owner)))
), upserted AS (
    UPDATE receivables r
    SET person_name = t.person_name,
        original_amount = t.total_amount,
        pending_amount = GREATEST(t.total_amount - COALESCE(r.paid_amount, 0), 0),
        status = CASE
            WHEN GREATEST(t.total_amount - COALESCE(r.paid_amount, 0), 0) <= 0.01 AND t.total_amount > 0 THEN 'completed'
            WHEN COALESCE(r.paid_amount, 0) > 0 THEN 'partial'
            ELSE 'pending'
        END,
        source_type = 'additional_card_auto',
        source_key = 'additional_cards:' || t.person_key,
        notes = 'AUTO_ADDITIONAL_CARD owner=' || t.person_name || '; cards=' || COALESCE(array_to_string(t.cards, ','), '') || '; movements=' || t.movement_count,
        updated_at = NOW()
    FROM totals t
    WHERE r.user_id = t.user_id
      AND r.source_key = 'additional_cards:' || t.person_key
    RETURNING r.id
)
INSERT INTO receivables (user_id, person_name, original_amount, paid_amount, pending_amount, status, source_type, source_key, notes)
SELECT
    t.user_id,
    t.person_name,
    t.total_amount,
    0,
    t.total_amount,
    CASE WHEN t.total_amount > 0 THEN 'pending' ELSE 'completed' END,
    'additional_card_auto',
    'additional_cards:' || t.person_key,
    'AUTO_ADDITIONAL_CARD owner=' || t.person_name || '; cards=' || COALESCE(array_to_string(t.cards, ','), '') || '; movements=' || t.movement_count
FROM totals t
WHERE NOT EXISTS (
    SELECT 1 FROM receivables r
    WHERE r.user_id = t.user_id
      AND r.source_key = 'additional_cards:' || t.person_key
);

-- Auto-apply incoming SINPE/income payments from Emily/Sidey only once.
WITH candidate_payments AS (
    SELECT
        t.user_id,
        t.id AS source_transaction_id,
        CASE
            WHEN LOWER(COALESCE(t.description,'') || ' ' || COALESCE(t.notes,'')) LIKE '%emily%' THEN 'Emily'
            WHEN LOWER(COALESCE(t.description,'') || ' ' || COALESCE(t.notes,'')) LIKE '%sidey%' THEN 'Sidey'
            ELSE NULL
        END AS person_name,
        t.amount
    FROM transactions t
    WHERE t.transaction_type IN ('income', 'reimbursement')
      AND COALESCE(t.amount, 0) > 0
), matched AS (
    SELECT cp.*, r.id AS receivable_id
    FROM candidate_payments cp
    JOIN receivables r
      ON r.user_id = cp.user_id
     AND LOWER(TRIM(r.person_name)) = LOWER(TRIM(cp.person_name))
     AND r.source_type = 'additional_card_auto'
    WHERE cp.person_name IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM receivable_payments rp
          WHERE rp.user_id = cp.user_id
            AND rp.source_transaction_id = cp.source_transaction_id
      )
), inserted AS (
    INSERT INTO receivable_payments (user_id, receivable_id, amount, source_transaction_id, notes)
    SELECT user_id, receivable_id, amount, source_transaction_id, 'Pago detectado automáticamente desde ingreso SINPE/reembolso.'
    FROM matched
    RETURNING receivable_id
), payment_totals AS (
    SELECT receivable_id, COALESCE(SUM(amount),0) AS total_paid
    FROM receivable_payments
    GROUP BY receivable_id
)
UPDATE receivables r
SET paid_amount = LEAST(r.original_amount, COALESCE(pt.total_paid, 0)),
    pending_amount = GREATEST(r.original_amount - COALESCE(pt.total_paid, 0), 0),
    status = CASE
        WHEN GREATEST(r.original_amount - COALESCE(pt.total_paid, 0), 0) <= 0.01 AND r.original_amount > 0 THEN 'completed'
        WHEN COALESCE(pt.total_paid, 0) > 0 THEN 'partial'
        ELSE 'pending'
    END,
    updated_at = NOW()
FROM payment_totals pt
WHERE r.id = pt.receivable_id;

COMMIT;
