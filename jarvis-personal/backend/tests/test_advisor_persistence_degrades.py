"""Without the advisor tables (created by migration 20260926125000) nothing is persisted and no DDL runs."""
from __future__ import annotations

from backend.advisor import core


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


class _Connection:
    def __init__(self):
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.queries.append(" ".join(query.split()))
        assert "to_regclass" in query, "only the schema check may run while the tables are missing"
        return _Result({"missing": list(core.STRATEGY_TABLES)})

    def commit(self):
        pass


def test_strategy_is_not_persisted_and_history_is_empty_without_the_tables(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(core, "get_connection", lambda: connection)
    monkeypatch.setattr(core, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(core, "get_current_user_id", lambda: 1)
    result = core._persist_strategy({"summary": "synthetic"})
    assert result["persisted"] is False and result["changed"] is False and result["strategy_hash"]
    assert core.get_strategy_history() == []
    assert len(connection.queries) == 2


class _PresentConnection(_Connection):
    def execute(self, query, params=()):
        self.queries.append(" ".join(query.split()))
        if "to_regclass" in query:
            return _Result({"missing": []})
        return _Result(None)


def test_the_current_strategy_upsert_returns_its_key(monkeypatch):
    # The connection wrapper appends "RETURNING id" to an INSERT without RETURNING;
    # advisor_current_strategy is keyed by workspace_id and has no id column.
    connection = _PresentConnection()
    monkeypatch.setattr(core, "get_connection", lambda: connection)
    monkeypatch.setattr(core, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(core, "get_current_user_id", lambda: 1)
    assert core._persist_strategy({"summary": "synthetic"})["changed"] is True
    upsert = next(q for q in connection.queries if q.startswith("INSERT INTO advisor_current_strategy"))
    assert upsert.endswith("RETURNING workspace_id")
