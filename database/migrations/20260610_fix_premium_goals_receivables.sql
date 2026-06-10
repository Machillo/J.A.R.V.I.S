-- Fix automatic receivables generated from additional-card purchases.
-- Keeps manual payments already registered and recalculates the original/pending
-- balance from the same transaction/candidate/card_alias source used by the
-- Additional Cards screen.

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

ALTER TABLE receivables ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS source_key TEXT;
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE receivables ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

WITH additional_totals AS (
    SELECT
        a.user_id,
        a.owner_label AS person_name,
        LOWER(TRIM(a.owner_label)) AS owner_key,
        COALESCE(SUM(t.amount), 0)::NUMERIC(14,2) AS original_amount,
        COUNT(DISTINCT t.id) AS movement_count,
        STRING_AGG(DISTINCT a.card_last4, ',' ORDER BY a.card_last4) AS cards
    FROM card_aliases a
    JOIN email_transaction_candidates c
      ON c.user_id = a.user_id
     AND c.card_last4 = a.card_last4
    JOIN transactions t
      ON t.user_id = c.user_id
     AND t.id = c.transaction_id
    WHERE COALESCE(a.is_primary, FALSE) = FALSE
      AND LOWER(TRIM(a.owner_label)) NOT IN ('kenneth', 'kenneth andres')
      AND t.transaction_type = 'expense'
      AND COALESCE(t.amount, 0) > 0
      AND COALESCE(c.status, '') IN ('confirmed', 'auto_saved', 'imported')
      AND COALESCE(c.status, '') NOT IN ('duplicate', 'rejected')
    GROUP BY a.user_id, a.owner_label
), upsert_existing AS (
    UPDATE receivables r
    SET person_name = t.person_name,
        original_amount = t.original_amount,
        pending_amount = GREATEST(t.original_amount - COALESCE(r.paid_amount, 0), 0),
        status = CASE
            WHEN GREATEST(t.original_amount - COALESCE(r.paid_amount, 0), 0) <= 0.01 THEN 'completed'
            WHEN COALESCE(r.paid_amount, 0) > 0 THEN 'partial'
            ELSE 'pending'
        END,
        source_type = 'additional_card_auto',
        notes = 'AUTO_ADDITIONAL_CARD owner=' || t.person_name || '; cards=' || COALESCE(t.cards, '') || '; movements=' || t.movement_count,
        updated_at = NOW()
    FROM additional_totals t
    WHERE r.user_id = t.user_id
      AND r.source_key = 'additional_cards:' || t.owner_key
    RETURNING r.source_key
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
    'AUTO_ADDITIONAL_CARD owner=' || t.person_name || '; cards=' || COALESCE(t.cards, '') || '; movements=' || t.movement_count,
    'additional_card_auto',
    'additional_cards:' || t.owner_key
FROM additional_totals t
WHERE NOT EXISTS (
    SELECT 1
    FROM receivables r
    WHERE r.user_id = t.user_id
      AND r.source_key = 'additional_cards:' || t.owner_key
);

COMMIT;
