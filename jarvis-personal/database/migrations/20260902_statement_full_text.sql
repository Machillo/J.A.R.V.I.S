BEGIN;

ALTER TABLE email_statement_documents
    ADD COLUMN IF NOT EXISTS extracted_text TEXT;

COMMENT ON COLUMN email_statement_documents.extracted_text IS
    'Texto completo extraído directamente del PDF para conciliación mensual.';

COMMIT;
