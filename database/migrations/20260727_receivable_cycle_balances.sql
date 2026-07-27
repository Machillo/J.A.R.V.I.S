BEGIN;

ALTER TABLE receivable_entries
    ADD COLUMN IF NOT EXISTS cycle_start DATE,
    ADD COLUMN IF NOT EXISTS cycle_end DATE,
    ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_receivable_entries_active_cycle
    ON receivable_entries(user_id, receivable_id, is_archived, cycle_start, cycle_end);

-- Archive the historical aggregate imported by the first ledger migration.
-- Historical payments must not cancel charges entered in a later cycle.
UPDATE receivable_entries
SET is_archived = TRUE
WHERE source_type IN ('legacy_payment', 'additional_card_auto')
  AND COALESCE(source_key, '') !~ '^additional_cards:[^:]+:[0-9]{4}-[0-9]{2}-[0-9]{2}$';

-- Preserve only a genuinely unpaid historical balance. If old payments were
-- equal to or greater than old charges, no carryover is created.
WITH legacy_totals AS (
    SELECT
        user_id,
        receivable_id,
        GREATEST(
            COALESCE(SUM(amount) FILTER (WHERE entry_type = 'charge'), 0)
            - COALESCE(SUM(amount) FILTER (WHERE entry_type = 'payment'), 0),
            0
        )::numeric(14,2) AS carry_amount
    FROM receivable_entries
    WHERE is_archived = TRUE
    GROUP BY user_id, receivable_id
), cycle AS (
    SELECT
        CASE
            WHEN EXTRACT(DAY FROM CURRENT_DATE)::int >= 21
                THEN make_date(EXTRACT(YEAR FROM CURRENT_DATE)::int, EXTRACT(MONTH FROM CURRENT_DATE)::int, 21)
            WHEN EXTRACT(MONTH FROM CURRENT_DATE)::int = 1
                THEN make_date(EXTRACT(YEAR FROM CURRENT_DATE)::int - 1, 12, 21)
            ELSE make_date(EXTRACT(YEAR FROM CURRENT_DATE)::int, EXTRACT(MONTH FROM CURRENT_DATE)::int - 1, 21)
        END AS cycle_start
)
INSERT INTO receivable_entries (
    user_id, receivable_id, entry_type, amount, description,
    entry_date, source_type, source_key, cycle_start, cycle_end, is_archived
)
SELECT
    lt.user_id,
    lt.receivable_id,
    'charge',
    lt.carry_amount,
    'Saldo pendiente arrastrado de ciclos anteriores',
    c.cycle_start,
    'carryover',
    'carryover:' || lt.receivable_id || ':' || c.cycle_start,
    c.cycle_start,
    (c.cycle_start + INTERVAL '1 month')::date,
    FALSE
FROM legacy_totals lt
CROSS JOIN cycle c
WHERE lt.carry_amount > 0
ON CONFLICT DO NOTHING;

-- Assign cycle metadata to active manual movements already created.
UPDATE receivable_entries e
SET cycle_start = CASE
        WHEN EXTRACT(DAY FROM e.entry_date)::int >= 21
            THEN make_date(EXTRACT(YEAR FROM e.entry_date)::int, EXTRACT(MONTH FROM e.entry_date)::int, 21)
        WHEN EXTRACT(MONTH FROM e.entry_date)::int = 1
            THEN make_date(EXTRACT(YEAR FROM e.entry_date)::int - 1, 12, 21)
        ELSE make_date(EXTRACT(YEAR FROM e.entry_date)::int, EXTRACT(MONTH FROM e.entry_date)::int - 1, 21)
    END
WHERE e.is_archived = FALSE
  AND e.cycle_start IS NULL;

UPDATE receivable_entries
SET cycle_end = (cycle_start + INTERVAL '1 month')::date
WHERE is_archived = FALSE
  AND cycle_start IS NOT NULL
  AND cycle_end IS NULL;


-- Correct the manually entered current-cycle amount that was rounded to a whole colon.
UPDATE receivable_entries
SET amount = 47048.50
WHERE user_id = 1
  AND receivable_id = 1
  AND entry_type = 'charge'
  AND source_type = 'manual_other'
  AND description = 'Varias compras'
  AND entry_date = DATE '2026-07-27'
  AND amount = 47049.00;

COMMIT;
