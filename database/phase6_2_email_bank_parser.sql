-- Fase 6.2 - Parser bancario real
-- Limpia pruebas antiguas del monitor y agrega documentos de estado de cuenta para conciliación.

CREATE TABLE IF NOT EXISTS email_statement_documents (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE CASCADE,
    bank TEXT NOT NULL,
    subject TEXT,
    statement_month TEXT,
    received_at TIMESTAMPTZ,
    attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    extracted_text_excerpt TEXT,
    status TEXT NOT NULL DEFAULT 'pending_reconciliation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, email_message_id)
);

-- Borrar únicamente movimientos que fueron guardados por el monitor de correos.
DELETE FROM transactions
WHERE source = 'email_monitor';

-- Borrar candidatos/mensajes anteriores para que el escaneo nuevo reprocesa con el parser limpio.
DELETE FROM email_statement_documents;
DELETE FROM email_transaction_candidates;
DELETE FROM email_ingested_messages;

UPDATE email_monitor_settings
SET last_scan_at = NULL,
    updated_at = NOW();
