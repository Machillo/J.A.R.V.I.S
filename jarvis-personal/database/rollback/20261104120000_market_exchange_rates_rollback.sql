-- Manual rollback of 20261104120000_market_exchange_rates (human decision). The rates can be read
-- again from the Banco Central; expenses already converted keep their amount and rate.
BEGIN;
DROP TABLE IF EXISTS public.market_exchange_rates;
COMMIT;
