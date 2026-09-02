BEGIN;

CREATE TABLE IF NOT EXISTS email_statement_reconciliation_lines (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workspace_id UUID NOT NULL,
    statement_document_id BIGINT NOT NULL REFERENCES email_statement_documents(id) ON DELETE CASCADE,
    transaction_date DATE NOT NULL,
    reference TEXT NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    debit NUMERIC(14,2) NOT NULL DEFAULT 0,
    credit NUMERIC(14,2) NOT NULL DEFAULT 0,
    balance NUMERIC(14,2),
    transaction_type TEXT NOT NULL,
    category TEXT NOT NULL,
    reconciliation_status TEXT NOT NULL CHECK (reconciliation_status IN ('matched','missing','ambiguous','ignored')),
    matched_transaction_id BIGINT,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, statement_document_id, reference, transaction_date, amount)
);

CREATE INDEX IF NOT EXISTS idx_statement_reconciliation_review
    ON email_statement_reconciliation_lines(workspace_id, statement_document_id, reconciliation_status);

COMMIT;
