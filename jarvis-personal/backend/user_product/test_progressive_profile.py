from backend.user_product import service


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, rows):
        self.rows = iter(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, _params=()):
        return _Result(next(self.rows))


def test_progressive_profile_reuses_observed_movements_without_creating_profile(monkeypatch):
    rows = [
        None,
        {"count": 1, "balance": 1200, "missing_interest": 1},
        {"count": 0, "current": 0, "target": 0},
        {
            "income_count": 4,
            "income_total": 2000,
            "income_months": 2,
            "expense_count": 6,
            "expense_total": 900,
            "expense_months": 3,
        },
    ]
    monkeypatch.setattr(service, "get_current_account_id", lambda: "account-1")
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: "workspace-1")
    monkeypatch.setattr(service, "get_connection", lambda: _Connection(rows))

    result = service.get_financial_situation()

    assert result["financial_profile"] is None
    assert result["observed"] == {
        "window_days": 90,
        "income_count": 4,
        "monthly_income_average": 1000.0,
        "expense_count": 6,
        "monthly_expense_average": 300.0,
    }
    assert result["debts"]["missing_interest"] == 1


def test_progressive_profile_does_not_divide_by_zero(monkeypatch):
    rows = [
        None,
        {"count": 0, "balance": 0, "missing_interest": 0},
        {"count": 0, "current": 0, "target": 0},
        {"income_count": 0, "income_total": 0, "income_months": 0, "expense_count": 0, "expense_total": 0, "expense_months": 0},
    ]
    monkeypatch.setattr(service, "get_current_account_id", lambda: "account-1")
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: "workspace-1")
    monkeypatch.setattr(service, "get_connection", lambda: _Connection(rows))

    result = service.get_financial_situation()

    assert result["observed"]["monthly_income_average"] == 0
    assert result["observed"]["monthly_expense_average"] == 0
