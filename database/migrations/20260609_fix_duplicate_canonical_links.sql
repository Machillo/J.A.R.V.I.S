-- Fix Fase 1.5 duplicate traceability.
-- Problem observed in production:
--   status = 'duplicate' but canonical_transaction_id IS NULL
-- This migration backfills semantic duplicate links and adds a defensive
-- constraint so the bug cannot silently return.

ALTER TABLE email_transaction_candidates
ADD COLUMN IF NOT EXISTS canonical_transaction_id BIGINT;

ALTER TABLE email_transaction_candidates
ADD COLUMN IF NOT EXISTS duplicate_of BIGINT;

CREATE INDEX IF NOT EXISTS idx_email_candidates_canonical
ON email_transaction_candidates(user_id, canonical_transaction_id);

CREATE INDEX IF NOT EXISTS idx_email_candidates_semantic_dedupe
ON email_transaction_candidates(user_id, transaction_date, amount, transaction_time, status);

-- 1) Fast path: older rows may have duplicate_of populated but not canonical_transaction_id.
UPDATE email_transaction_candidates
SET canonical_transaction_id = duplicate_of,
    updated_at = NOW()
WHERE status = 'duplicate'
  AND canonical_transaction_id IS NULL
  AND duplicate_of IS NOT NULL;

-- 2) Backfill orphan duplicates by the business rule:
--    same amount + same date + ±10 minutes when both sides have transaction_time.
WITH ranked_matches AS (
    SELECT
        duplicate_row.id AS duplicate_id,
        canonical_row.id AS canonical_id,
        ROW_NUMBER() OVER (
            PARTITION BY duplicate_row.id
            ORDER BY
                canonical_row.created_at ASC,
                canonical_row.id ASC
        ) AS match_rank
    FROM email_transaction_candidates duplicate_row
    JOIN email_transaction_candidates canonical_row
      ON canonical_row.user_id = duplicate_row.user_id
     AND canonical_row.id <> duplicate_row.id
     AND canonical_row.transaction_date = duplicate_row.transaction_date
     AND ABS(canonical_row.amount - duplicate_row.amount) < 0.01
     AND canonical_row.status IN ('pending', 'confirmed', 'auto_saved')
     AND (
            duplicate_row.transaction_time IS NULL
         OR canonical_row.transaction_time IS NULL
         OR ABS(EXTRACT(EPOCH FROM (
                (duplicate_row.transaction_date + duplicate_row.transaction_time)
              - (canonical_row.transaction_date + canonical_row.transaction_time)
            ))) <= 600
     )
    WHERE duplicate_row.status = 'duplicate'
      AND duplicate_row.canonical_transaction_id IS NULL
), chosen_matches AS (
    SELECT duplicate_id, canonical_id
    FROM ranked_matches
    WHERE match_rank = 1
)
UPDATE email_transaction_candidates target
SET canonical_transaction_id = chosen_matches.canonical_id,
    duplicate_of = COALESCE(target.duplicate_of, chosen_matches.canonical_id),
    review_reason = COALESCE(NULLIF(target.review_reason, ''), 'Duplicado semántico vinculado a su transacción canónica.'),
    updated_at = NOW()
FROM chosen_matches
WHERE target.id = chosen_matches.duplicate_id;

-- 3) Keep canonical rows self-referenced. This makes reporting simpler:
--    duplicate rows point to the canonical id; canonical rows point to themselves.
UPDATE email_transaction_candidates
SET canonical_transaction_id = id,
    updated_at = NOW()
WHERE status IN ('pending', 'confirmed', 'auto_saved')
  AND canonical_transaction_id IS NULL;

-- 4) Enforce future consistency without blocking deployment if old rows from
--    saved transactions remain. A duplicate is valid if it points to a candidate
--    canonical row OR to an already-saved transaction_id.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_email_candidate_duplicate_trace'
    ) THEN
        ALTER TABLE email_transaction_candidates
        ADD CONSTRAINT chk_email_candidate_duplicate_trace
        CHECK (
            status <> 'duplicate'
            OR canonical_transaction_id IS NOT NULL
            OR transaction_id IS NOT NULL
        ) NOT VALID;
    END IF;
END $$;
