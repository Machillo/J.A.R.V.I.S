-- FINVA paid beta, privacy-safe product telemetry and feedback operations.
-- Runtime creates the same additive schema so deployments remain migration-safe.
CREATE TABLE IF NOT EXISTS finva_beta_programs (
  code TEXT PRIMARY KEY, active BOOLEAN NOT NULL DEFAULT TRUE,
  beta_duration_months INTEGER NOT NULL DEFAULT 3,
  basic_slots INTEGER NOT NULL DEFAULT 15, vip_slots INTEGER NOT NULL DEFAULT 15,
  basic_beta_price_crc NUMERIC(12,2) NOT NULL DEFAULT 1990, vip_beta_price_crc NUMERIC(12,2) NOT NULL DEFAULT 3990,
  basic_regular_price_crc NUMERIC(12,2) NOT NULL DEFAULT 2990, vip_regular_price_crc NUMERIC(12,2) NOT NULL DEFAULT 5990,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO finva_beta_programs(code) VALUES('beta-2026-01') ON CONFLICT(code) DO NOTHING;

CREATE TABLE IF NOT EXISTS billing_orders (
  id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, workspace_id UUID,
  plan_code TEXT NOT NULL CHECK(plan_code IN ('basic','vip')), amount NUMERIC(12,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC',
  status TEXT NOT NULL DEFAULT 'payment_pending' CHECK(status IN ('payment_pending','paid','failed','canceled','expired','refunded')),
  provider TEXT NOT NULL DEFAULT 'sandbox', provider_order_id TEXT, beta_code TEXT, beta_price BOOLEAN NOT NULL DEFAULT TRUE,
  consent_version TEXT NOT NULL, consent_at TIMESTAMPTZ NOT NULL, paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_billing_orders_status ON billing_orders(status,created_at DESC);
CREATE TABLE IF NOT EXISTS billing_subscriptions (
  account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE, workspace_id UUID,
  plan_code TEXT NOT NULL CHECK(plan_code IN ('basic','vip')),
  status TEXT NOT NULL CHECK(status IN ('payment_pending','active','past_due','canceled','expired','refunded')),
  provider TEXT NOT NULL DEFAULT 'sandbox', provider_subscription_id TEXT, beta_code TEXT,
  beta_ends_at TIMESTAMPTZ, current_period_start TIMESTAMPTZ, current_period_end TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE, paid_price_crc NUMERIC(12,2), regular_price_crc NUMERIC(12,2),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS product_events (
  id BIGSERIAL PRIMARY KEY, account_id UUID REFERENCES accounts(id) ON DELETE SET NULL, workspace_id UUID,
  event_name TEXT NOT NULL, plan_code TEXT, surface TEXT NOT NULL, success BOOLEAN NOT NULL DEFAULT TRUE,
  duration_bucket TEXT, app_version TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_product_events_created ON product_events(created_at DESC);
CREATE TABLE IF NOT EXISTS feedback_reports (
  id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, workspace_id UUID,
  category TEXT NOT NULL, subject TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
  plan_code TEXT, app_version TEXT, owner_notes TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), resolved_at TIMESTAMPTZ
);
