-- Rollback of 20260926120000_retire_offstore_billing.sql: recreate the retired
-- tables EMPTY (they were empty when retired) with their last schema, RLS on and
-- closed to the Data API roles. Only needed to redeploy code older than this PR.
-- Run under docs/security/migration-safety-protocol.md (BACKUP_VERIFIED, second reviewer).

BEGIN;

SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS public.finva_beta_programs (
  code TEXT PRIMARY KEY, active BOOLEAN NOT NULL DEFAULT TRUE,
  beta_duration_months INTEGER NOT NULL DEFAULT 3,
  basic_slots INTEGER NOT NULL DEFAULT 15, vip_slots INTEGER NOT NULL DEFAULT 15,
  basic_beta_price_crc NUMERIC(12,2) NOT NULL DEFAULT 1990, vip_beta_price_crc NUMERIC(12,2) NOT NULL DEFAULT 3990,
  basic_regular_price_crc NUMERIC(12,2) NOT NULL DEFAULT 2990, vip_regular_price_crc NUMERIC(12,2) NOT NULL DEFAULT 4990,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO public.finva_beta_programs(code) VALUES ('beta-2026-01') ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.billing_orders (
  id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE, workspace_id UUID,
  plan_code TEXT NOT NULL CHECK (plan_code IN ('basic','vip')), amount NUMERIC(12,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC',
  status TEXT NOT NULL DEFAULT 'payment_pending' CHECK (status IN ('payment_pending','paid','failed','canceled','expired','refunded')),
  provider TEXT NOT NULL DEFAULT 'sinpe_mobile', provider_order_id TEXT, beta_code TEXT, beta_price BOOLEAN NOT NULL DEFAULT TRUE,
  payment_code TEXT, code_expires_at TIMESTAMPTZ,
  receipt_filename TEXT, receipt_content_type TEXT, receipt_size INTEGER, receipt_sha256 TEXT, receipt_data BYTEA,
  receipt_submitted_at TIMESTAMPTZ, receipt_status TEXT NOT NULL DEFAULT 'not_submitted',
  verified_at TIMESTAMPTZ, verification_source TEXT, bank_reference TEXT, payer_name TEXT,
  consent_version TEXT NOT NULL, consent_at TIMESTAMPTZ NOT NULL, paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_billing_orders_status ON public.billing_orders(status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_orders_payment_code ON public.billing_orders(payment_code) WHERE payment_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_orders_receipt_sha256 ON public.billing_orders(receipt_sha256) WHERE receipt_sha256 IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.billing_subscriptions (
  account_id UUID PRIMARY KEY REFERENCES public.accounts(id) ON DELETE CASCADE, workspace_id UUID,
  plan_code TEXT NOT NULL CHECK (plan_code IN ('basic','vip')),
  status TEXT NOT NULL CHECK (status IN ('payment_pending','active','past_due','canceled','expired','refunded')),
  provider TEXT NOT NULL DEFAULT 'sandbox', provider_subscription_id TEXT, beta_code TEXT,
  beta_ends_at TIMESTAMPTZ, current_period_start TIMESTAMPTZ, current_period_end TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE, paid_price_crc NUMERIC(12,2), regular_price_crc NUMERIC(12,2),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.finva_beta_programs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_subscriptions ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.finva_beta_programs, public.billing_orders, public.billing_subscriptions FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON SEQUENCE public.billing_orders_id_seq FROM anon, authenticated;

COMMIT;
