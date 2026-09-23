import pytest

from backend.auth import data_export
from backend.auth.current_user import reset_current_user, set_current_user


ACCOUNT = "11111111-1111-1111-1111-111111111111"
WORKSPACE = "33333333-3333-3333-3333-333333333333"


class Result:
    def __init__(self, rows=None): self.rows = rows or []
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class Connection:
    def __init__(self): self.queries = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def rollback(self): pass
    def commit(self): pytest.fail("Export must be read-only")
    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "information_schema.columns" in normalized:
            return Result([
                *({"table_name": "finva_gmail_connections", "column_name": c} for c in ("id", "account_id", "workspace_id", "google_email", "refresh_token_secret_id")),
                *({"table_name": "transactions", "column_name": c} for c in ("id", "workspace_id", "amount")),
                *({"table_name": "currencies", "column_name": c} for c in ("code", "name")),
                *({"table_name": "workspaces", "column_name": c} for c in ("id", "owner_account_id")),
            ])
        if normalized.startswith("SELECT id, primary_email"):
            return Result([{"id": ACCOUNT, "primary_email": "person@example.com"}])
        if normalized.startswith("SELECT id, name, workspace_type"):
            return Result([{"id": WORKSPACE, "name": "Personal"}])
        if 'FROM "finva_gmail_connections"' in normalized:
            return Result([{"id": 1, "google_email": "person@gmail.com"}])
        if 'FROM "transactions"' in normalized:
            return Result([{"id": 7, "amount": 1500.0}])
        return Result()


def test_export_includes_owned_tables_and_never_secrets(monkeypatch):
    conn = Connection()
    monkeypatch.setattr(data_export, "get_connection", lambda: conn)
    token = set_current_user({"id": 42, "account_id": ACCOUNT, "workspace_id": WORKSPACE})
    try:
        result = data_export.export_current_account_data()
    finally:
        reset_current_user(token)

    assert set(result["data"]) == {"finva_gmail_connections", "transactions"}
    gmail_query, gmail_params = next(q for q in conn.queries if 'FROM "finva_gmail_connections"' in q[0])
    assert "refresh_token_secret_id" not in gmail_query
    assert gmail_params[0] == ACCOUNT and gmail_params[1] == [WORKSPACE]
    tx_query, tx_params = next(q for q in conn.queries if 'FROM "transactions"' in q[0])
    assert "account_id" not in tx_query and tx_params[0] == [WORKSPACE]
    assert not any('FROM "currencies"' in q[0] or 'FROM "workspaces" WHERE' in q[0] for q in conn.queries)


def test_export_rejects_unexpected_identifiers():
    with pytest.raises(ValueError):
        data_export._quote('transactions"; DROP TABLE accounts; --')
