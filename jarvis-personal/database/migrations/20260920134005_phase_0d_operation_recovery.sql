BEGIN;

CREATE TABLE IF NOT EXISTS public.operation_idempotency (
  account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  method TEXT NOT NULL,
  path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'processing'
    CHECK (status IN ('processing', 'completed')),
  response_status INTEGER,
  response_body JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours',
  PRIMARY KEY (account_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_operation_idempotency_expiry
  ON public.operation_idempotency(expires_at);

ALTER TABLE public.operation_idempotency ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.operation_idempotency FROM anon, authenticated;

COMMIT;
