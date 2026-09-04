-- JARVIS 05: canonical real-world financial accounts and balance history.
CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_name TEXT NOT NULL,
    bank_name TEXT NOT NULL DEFAULT '',
    account_type TEXT NOT NULL DEFAULT 'checking',
    account_last4 TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'CRC',
    current_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
    annual_interest_rate NUMERIC(8,4) NOT NULL DEFAULT 0,
    balance_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'manual',
    include_in_net_worth BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, account_name, account_last4)
);

ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS account_type TEXT NOT NULL DEFAULT 'checking';
ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS annual_interest_rate NUMERIC(8,4) NOT NULL DEFAULT 0;
ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS balance_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS include_in_net_worth BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS account_balance_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    financial_account_id BIGINT NOT NULL REFERENCES account_balances(id) ON DELETE CASCADE,
    balance NUMERIC(18,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CRC',
    balance_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'manual',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS financial_account_id BIGINT REFERENCES account_balances(id) ON DELETE SET NULL;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS financial_account_id BIGINT REFERENCES account_balances(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_account_balances_workspace ON account_balances(workspace_id, is_active);
CREATE INDEX IF NOT EXISTS idx_account_history_account_date ON account_balance_history(financial_account_id, balance_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_financial_account ON transactions(workspace_id, financial_account_id, transaction_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_account_balances_identity ON account_balances(workspace_id, account_name, account_last4);

INSERT INTO account_balances(user_id, workspace_id, account_name, bank_name, account_type, account_last4, currency, current_balance, source)
SELECT MIN(user_id), workspace_id, BTRIM(account),
       CASE WHEN LOWER(account) LIKE 'bac%' THEN 'BAC' WHEN LOWER(account) LIKE 'multimoney%' THEN 'MultiMoney' ELSE '' END,
       CASE WHEN LOWER(account) LIKE '%tarjeta%' OR account ~ '\*{4}[0-9]{4}' THEN 'credit_card' ELSE 'checking' END,
       COALESCE((regexp_match(account, '([0-9]{4})\s*$'))[1], ''), 'CRC', 0, 'transaction_backfill'
FROM transactions
WHERE workspace_id IS NOT NULL AND NULLIF(BTRIM(account), '') IS NOT NULL
GROUP BY workspace_id, BTRIM(account)
ON CONFLICT(workspace_id, account_name, account_last4) DO NOTHING;

UPDATE transactions t
SET financial_account_id = a.id
FROM account_balances a
WHERE t.workspace_id = a.workspace_id
  AND LOWER(BTRIM(t.account)) = LOWER(BTRIM(a.account_name))
  AND t.financial_account_id IS NULL;

CREATE OR REPLACE FUNCTION jarvis_link_financial_account() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.financial_account_id IS NULL AND NULLIF(BTRIM(NEW.account),'') IS NOT NULL THEN
        SELECT id INTO NEW.financial_account_id
        FROM account_balances
        WHERE workspace_id=NEW.workspace_id AND is_active=TRUE
          AND (LOWER(BTRIM(account_name))=LOWER(BTRIM(NEW.account))
               OR (account_last4<>'' AND NEW.account LIKE CHR(37) || account_last4))
        ORDER BY CASE WHEN LOWER(BTRIM(account_name))=LOWER(BTRIM(NEW.account)) THEN 0 ELSE 1 END,id
        LIMIT 1;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_transactions_financial_account ON transactions;
CREATE TRIGGER trg_transactions_financial_account
BEFORE INSERT OR UPDATE OF account, financial_account_id ON transactions
FOR EACH ROW EXECUTE FUNCTION jarvis_link_financial_account();
