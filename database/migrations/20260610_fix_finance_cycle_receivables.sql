-- Fix current automatic receivables that were created with 0 because the
-- previous sync depended on transactions.card metadata that does not exist.
-- This migration recalculates additional-card receivables from accepted email
-- candidates and their card aliases. It is safe to re-run.

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

WITH additional_totals AS (
    SELECT
        a.user_id,
        a.owner_label AS person_name,
        LOWER(a.owner_label) AS owner_key,
        COALESCE(SUM(COALESCE(t.amount, c.amount)), 0)::NUMERIC(14,2) AS original_amount,
        COUNT(*) AS movement_count
    FROM card_aliases a
    JOIN email_transaction_candidates c
      ON c.user_id = a.user_id
     AND c.card_last4 = a.card_last4
    LEFT JOIN transactions t
      ON t.user_id = c.user_id
     AND t.id = c.transaction_id
    WHERE COALESCE(a.is_primary, FALSE) = FALSE
      AND LOWER(TRIM(a.owner_label)) NOT IN ('kenneth', 'kenneth andres')
      AND COALESCE(c.transaction_type, t.transaction_type, '') = 'expense'
      AND COALESCE(c.status, '') IN ('confirmed', 'auto_saved', 'imported')
      AND COALESCE(c.status, '') NOT IN ('duplicate', 'rejected')
      AND COALESCE(COALESCE(t.amount, c.amount), 0) > 0
    GROUP BY a.user_id, a.owner_label
), updated AS (
    UPDATE receivables r
    SET
        person_name = t.person_name,
        original_amount = t.original_amount,
        pending_amount = GREATEST(t.original_amount - COALESCE(r.paid_amount, 0), 0),
        status = CASE
            WHEN GREATEST(t.original_amount - COALESCE(r.paid_amount, 0), 0) <= 0.01 THEN 'completed'
            WHEN COALESCE(r.paid_amount, 0) > 0 THEN 'partial'
            ELSE 'pending'
        END,
        source_type = 'additional_card_auto',
        notes = 'AUTO_ADDITIONAL_CARD recalculado desde email candidates; movements=' || t.movement_count,
        updated_at = NOW()
    FROM additional_totals t
    WHERE r.user_id = t.user_id
      AND r.source_key = 'additional_cards:' || t.owner_key
    RETURNING r.user_id, r.source_key
)
INSERT INTO receivables (
    user_id, person_name, original_amount, paid_amount, pending_amount,
    status, notes, source_type, source_key
)
SELECT
    t.user_id,
    t.person_name,
    t.original_amount,
    0,
    t.original_amount,
    CASE WHEN t.original_amount > 0 THEN 'pending' ELSE 'completed' END,
    'AUTO_ADDITIONAL_CARD recalculado desde email candidates; movements=' || t.movement_count,
    'additional_card_auto',
    'additional_cards:' || t.owner_key
FROM additional_totals t
WHERE NOT EXISTS (
    SELECT 1
    FROM receivables r
    WHERE r.user_id = t.user_id
      AND r.source_key = 'additional_cards:' || t.owner_key
);
