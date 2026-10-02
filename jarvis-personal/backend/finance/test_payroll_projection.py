"""Received salary replaces its projected share in the cycle; it never adds on top of it."""
from datetime import date

from backend.auth.current_user import reset_current_user, set_current_user
from backend.finance import payroll_receipts, service

TODAY = date(2030, 1, 25)


def test_received_salary_replaces_the_projection_week_by_week():
    projected = 400000.0                                         # the month's projected net (base + OT/bonus events)
    weeks = [{"category": "Salario", "amount": 100000.0}] * 2    # two weekly deposits received so far
    assert payroll_receipts.pending_projection(projected, payroll_receipts.salary_received(weeks)) == 200000.0
    four = [{"category": "Salario", "amount": 100000.0}] * 4
    assert payroll_receipts.pending_projection(projected, payroll_receipts.salary_received(four)) == 0.0
    five = four + [{"category": "Horas extra", "amount": 50000.0}]  # more received than projected: nothing still pending
    assert payroll_receipts.pending_projection(projected, payroll_receipts.salary_received(five)) == 0.0


def test_non_salary_income_does_not_consume_the_salary_projection():
    rows = [{"category": "Inversión", "amount": 900.0}, {"category": "Otros ingresos", "amount": 5000.0}, {"category": "Salario", "amount": 1000.0}]
    assert payroll_receipts.salary_received(rows) == 1000.0
    assert payroll_receipts.pending_projection(10000.0, 1000.0) == 9000.0


class _Rows:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class _Cycle:
    """Returns two weekly salary deposits for the cycle's income query, nothing else."""
    def __enter__(self): return self
    def __exit__(self, *_a): return False
    def commit(self): pass

    def execute(self, query, params=()):
        if "= 'income'" in query and "FROM transactions" in query:
            return _Rows([{"id": i, "transaction_date": TODAY.isoformat(), "description": "Planilla", "amount": 100000.0,
                           "transaction_type": "income", "category": "Salario", "account": None, "source": "test", "notes": None,
                           "created_at": None} for i in (1, 2)])
        return _Rows([])


def test_the_cycle_never_counts_projected_and_received_salary_twice(monkeypatch):
    monkeypatch.setattr(service, "get_connection", lambda: _Cycle())
    monkeypatch.setattr(service, "calculate_monthly_salary_projection", lambda: {"results": {"base_net": 400000.0}})
    token = set_current_user({"id": 7, "account_id": "a", "workspace_id": "00000000-0000-4000-8000-000000000001", "role": "owner"})
    try:
        report = service.get_financial_cycle_report(as_of=TODAY)
    finally:
        reset_current_user(token)
    # 400k projected for the month: 200k already received + 200k still to come, not 600k.
    assert report["cashflow"]["real_balance"] == 400000.0
    income = report["income"]
    assert income["expected_total"] == 400000.0 and income["received_from_transactions"] == 200000.0
    assert income["salary_received"] == 200000.0 and income["pending_projection"] == 200000.0
