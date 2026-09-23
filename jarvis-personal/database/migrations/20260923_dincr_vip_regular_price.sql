-- Forward-only correction. Preserve historical orders, paid amounts and subscriptions.
-- The original 20260910 migration remains unchanged for applied installations.
ALTER TABLE IF EXISTS finva_beta_programs
  ALTER COLUMN vip_regular_price_crc SET DEFAULT 4990;

UPDATE finva_beta_programs
SET vip_regular_price_crc = 4990, updated_at = NOW()
WHERE vip_regular_price_crc = 5990;
