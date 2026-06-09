-- Fase Email Parser Real 1.1
-- Corrige ingesta Gmail: query amplia por remitente, cuerpo completo, adjuntos, logs y reanálisis limpio.

ALTER TABLE email_ingested_messages
  ADD COLUMN IF NOT EXISTS raw_body TEXT,
  ADD COLUMN IF NOT EXISTS body_text TEXT,
  ADD COLUMN IF NOT EXISTS attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ADD COLUMN IF NOT EXISTS attachment_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS parse_reason TEXT;

CREATE TABLE IF NOT EXISTS email_parser_logs (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  provider_message_id TEXT,
  sender TEXT,
  subject TEXT,
  bank TEXT,
  action TEXT NOT NULL,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_parser_logs_user_created
ON email_parser_logs(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_ingested_messages_user_received
ON email_ingested_messages(user_id, received_at DESC);

-- Query amplia: Gmail trae remitentes financieros; el parser decide qué es movimiento real.
UPDATE email_monitor_settings
SET gmail_query = '(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr OR from:alerta@baccredomatic.com OR from:estadosdecuenta@baccredomatic.cr OR from:estadodecuenta@baccredomatic.cr OR from:info@info.baccredomatic.net OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com OR from:bancopopular.fi.cr OR from:bancopopular OR from:popular)',
    auto_commit_confidence = 999,
    updated_at = NOW()
WHERE user_id = 1;

-- Estados de cuenta ya no deben vivir como candidatos de monto 0.
DELETE FROM email_transaction_candidates
WHERE user_id = 1
  AND transaction_type = 'statement';

-- Reprocesamiento seguro: conserva transacciones confirmadas, pero permite que el nuevo parser vuelva a leer ignorados/procesados viejos.
DELETE FROM email_ingested_messages im
WHERE im.user_id = 1
  AND im.provider = 'gmail'
  AND NOT EXISTS (
    SELECT 1
    FROM email_transaction_candidates c
    WHERE c.email_message_id = im.id
      AND c.user_id = im.user_id
      AND c.status IN ('confirmed', 'auto_saved')
  );
