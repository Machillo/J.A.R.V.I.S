import pytest

from backend.financial_lifecycle import snapshots
from backend.financial_lifecycle.state import _monthly_ledger


def test_monthly_ledger_uses_latest_when_current_period_missing(monkeypatch):
    monkeypatch.setattr("backend.financial_lifecycle.state.date", _FakeDate)
    flow = {
        "months": [
            {"month": "2026-07", "income": 100, "expenses": 40, "debt_payments": 10, "net_operational": 50},
            {"month": "2026-08", "income": 120, "expenses": 50, "debt_payments": 10, "net_operational": 60},
        ]
    }
    assert _monthly_ledger(flow) == {
        "income": 120.0,
        "expenses": 50.0,
        "debt_payments": 10.0,
        "net_operational": 60.0,
    }


def test_monthly_ledger_prefers_current_period(monkeypatch):
    monkeypatch.setattr("backend.financial_lifecycle.state.date", _FakeDate)
    flow = {
        "months": [
            {"month": "2026-08", "income": 120, "expenses": 50, "debt_payments": 10, "net_operational": 60},
            {"month": "2026-09", "income": 200, "expenses": 70, "debt_payments": 20, "net_operational": 110},
        ]
    }
    assert _monthly_ledger(flow)["net_operational"] == 110.0


class _FakeDate:
    @classmethod
    def today(cls):
        class Today:
            def strftime(self, pattern):
                return "2026-09"
        return Today()


class _Result:
    def __init__(self, *, one=None, all_rows=None):
        self.one = one
        self.all_rows = all_rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.all_rows


class _Connection:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return next(self.results)

    def commit(self):
        self.committed = True


def test_snapshot_capture_binds_authenticated_workspace_and_account(monkeypatch):
    state = {"period": "2026-09", "schema_version": "financial-state-v1"}
    connection = _Connection([_Result(one={"id": 7, "snapshot_date": "2026-09-20"})])
    monkeypatch.setattr(snapshots, "build_financial_state", lambda: state)
    monkeypatch.setattr(snapshots, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(snapshots, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(snapshots, "get_connection", lambda: connection)

    result = snapshots.capture_financial_snapshot()

    assert connection.calls[0][1][:2] == ("workspace-a", "account-a")
    assert connection.committed is True
    assert result["snapshot"]["id"] == 7


def test_snapshot_history_query_is_scoped_to_authenticated_workspace(monkeypatch):
    connection = _Connection([_Result(all_rows=[{"id": 1}])])
    monkeypatch.setattr(snapshots, "get_current_workspace_id", lambda: "workspace-b")
    monkeypatch.setattr(snapshots, "get_connection", lambda: connection)

    assert snapshots.list_financial_snapshots(limit=999) == [{"id": 1}]
    query, params = connection.calls[0]
    assert "WHERE workspace_id=%s" in query
    assert params == ("workspace-b", 366)


def test_progress_baseline_query_is_scoped_to_authenticated_workspace(monkeypatch):
    connection = _Connection([_Result(one=None)])
    monkeypatch.setattr(snapshots, "build_financial_state", lambda: {"schema_version": "financial-state-v1"})
    monkeypatch.setattr(snapshots, "get_current_workspace_id", lambda: "workspace-c")
    monkeypatch.setattr(snapshots, "get_connection", lambda: connection)

    result = snapshots.get_financial_progress()

    assert result["status"] == "BASELINE"
    assert connection.calls[0][1] == ("workspace-c",)


def test_monthly_review_query_is_scoped_to_workspace_and_period(monkeypatch):
    connection = _Connection([_Result(all_rows=[])])
    monkeypatch.setattr(snapshots, "get_current_workspace_id", lambda: "workspace-d")
    monkeypatch.setattr(snapshots, "get_connection", lambda: connection)

    result = snapshots.get_monthly_review("2026-08")

    assert result["status"] == "BASELINE"
    assert connection.calls[0][1][0] == "workspace-d"
    assert str(connection.calls[0][1][1]) == "2026-08-01"
    assert str(connection.calls[0][1][2]) == "2026-09-01"


def test_monthly_review_rejects_invalid_period_before_querying_database():
    with pytest.raises(ValueError, match="YYYY-MM"):
        snapshots.get_monthly_review("2026-13")
