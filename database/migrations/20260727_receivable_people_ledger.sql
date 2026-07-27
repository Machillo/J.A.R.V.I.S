BEGIN;

CREATE TABLE IF NOT EXISTS receivable_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    description TEXT NOT NULL DEFAULT '',
    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_key TEXT,
    source_transaction_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_receivable_entries_account
    ON receivable_entries(user_id, receivable_id, entry_date DESC, id DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_entries_source_key
    ON receivable_entries(user_id, source_key)
    WHERE source_key IS NOT NULL;

-- Preserve legacy manual balances as opening charges.
INSERT INTO receivable_entries (
    user_id, receivable_id, entry_type, amount, description,
    entry_date, source_type, source_key
)
SELECT
    r.user_id,
    r.id,
    'charge',
    r.original_amount,
    COALESCE(NULLIF(BTRIM(r.notes), ''), 'Saldo inicial de ' || r.person_name),
    r.created_at::date,
    'legacy',
    'legacy_receivable:' || r.id
FROM receivables r
WHERE r.source_type <> 'additional_card_auto'
  AND r.original_amount > 0
ON CONFLICT DO NOTHING;

-- Preserve payments without duplicating entries already linked to the same transaction.
INSERT INTO receivable_entries (
    user_id, receivable_id, entry_type, amount, description,
    entry_date, source_type, source_key, source_transaction_id
)
SELECT
    rp.user_id,
    rp.receivable_id,
    'payment',
    rp.amount,
    COALESCE(NULLIF(BTRIM(rp.notes), ''), 'Pago registrado'),
    rp.created_at::date,
    'legacy_payment',
    'legacy_receivable_payment:' || rp.id,
    rp.source_transaction_id
FROM receivable_payments rp
WHERE NOT EXISTS (
    SELECT 1
    FROM receivable_entries e
    WHERE e.user_id = rp.user_id
      AND (
            e.source_key = 'legacy_receivable_payment:' || rp.id
         OR (rp.source_transaction_id IS NOT NULL AND e.source_transaction_id = rp.source_transaction_id)
      )
)
ON CONFLICT DO NOTHING;

COMMIT;
