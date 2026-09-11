-- Additive SINPE Mobile verification for FINVA paid beta orders.
-- Safe to run when 20260910_finva_beta_product_ops.sql was already applied.
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS payment_code TEXT;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS code_expires_at TIMESTAMPTZ;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_filename TEXT;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_content_type TEXT;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_size INTEGER;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_sha256 TEXT;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_data BYTEA;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_submitted_at TIMESTAMPTZ;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_status TEXT NOT NULL DEFAULT 'not_submitted';
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS verification_source TEXT;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS bank_reference TEXT;
ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS payer_name TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_orders_payment_code
  ON billing_orders(payment_code) WHERE payment_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_orders_receipt_sha256
  ON billing_orders(receipt_sha256) WHERE receipt_sha256 IS NOT NULL;
