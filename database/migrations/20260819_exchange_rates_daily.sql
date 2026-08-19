BEGIN;

CREATE TABLE IF NOT EXISTS exchange_rates (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    rate_date DATE NOT NULL,
    currency TEXT NOT NULL,
    exchange_rate NUMERIC(14, 6) NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, rate_date, currency)
);

CREATE INDEX IF NOT EXISTS idx_exchange_rates_user_date_currency
ON exchange_rates(user_id, rate_date, currency);

-- Preserve rates already stored in historical USD transactions. If several
-- transactions on one day have a rate, the latest transaction wins.
INSERT INTO exchange_rates (user_id, rate_date, currency, exchange_rate, source)
SELECT DISTINCT ON (user_id, transaction_date::date, UPPER(original_currency))
       user_id, transaction_date::date, UPPER(original_currency), exchange_rate, 'historical_transaction'
FROM transactions
WHERE UPPER(COALESCE(original_currency, '')) = 'USD'
  AND exchange_rate IS NOT NULL
  AND exchange_rate > 0
ORDER BY user_id, transaction_date::date, UPPER(original_currency), id DESC
ON CONFLICT (user_id, rate_date, currency)
DO UPDATE SET exchange_rate = EXCLUDED.exchange_rate,
              source = EXCLUDED.source,
              updated_at = NOW();

-- Apply a known historical rate to any old USD transaction that was still pending.
UPDATE transactions t
SET exchange_rate = er.exchange_rate,
    amount = ROUND(t.original_amount * er.exchange_rate, 2)
FROM exchange_rates er
WHERE er.user_id = t.user_id
  AND er.rate_date = t.transaction_date::date
  AND UPPER(er.currency) = 'USD'
  AND UPPER(COALESCE(t.original_currency, '')) = 'USD'
  AND t.original_amount IS NOT NULL
  AND t.exchange_rate IS NULL;

COMMIT;
