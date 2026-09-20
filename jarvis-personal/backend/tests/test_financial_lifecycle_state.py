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
