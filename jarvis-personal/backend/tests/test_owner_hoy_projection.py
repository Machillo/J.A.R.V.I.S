"""The Owner's Hoy: his statement counted whole from its first day (synthetic figures only)."""
from datetime import date
from decimal import Decimal

import pytest

from backend.ai import owner_hoy_projection as projection

START, END = date(2026, 10, 22), date(2026, 11, 22)  # 22 Oct to 21 Nov
DEBTS = [
    {"id": 1, "name": "Préstamo A", "monthly_payment": 50_000.0, "debt_type": "personal", "next_payment_date": "2026-11-10"},
    {"id": 2, "name": "Préstamo B", "monthly_payment": 30_000.0, "debt_type": "personal", "next_payment_date": None},
    {"id": 3, "name": "Compra a tasa cero", "monthly_payment": 9_000.0, "debt_type": "tasa_cero", "next_payment_date": "2026-11-02"},
    {"id": 4, "name": "Préstamo C", "monthly_payment": 20_000.0, "debt_type": "personal", "next_payment_date": "2026-12-03"},
    {"id": 5, "name": "Préstamo D", "monthly_payment": None, "debt_type": "personal", "next_payment_date": "2026-11-15"},
]


def test_every_installment_of_the_statement_counts_from_its_first_day():
    pending = projection.pending_installments(DEBTS, set(), END)
    # A, B and the card plan (the schedule posts it like any debt); C falls after it, D's payment is unknown.
    assert pending == {"total": Decimal("89000.0"), "unknown": 1}


def test_an_installment_already_paid_is_not_counted_again():
    assert projection.pending_installments(DEBTS, {1}, END)["total"] == Decimal("39000.0")
    assert projection.pending_installments(DEBTS, {1, 3}, END)["total"] == Decimal("30000.0")


FIXED = [
    {"fixed_expense": {"name": "Casa", "category": "Vivienda"}, "due_date": "2026-11-01", "due_this_month": True,
     "status": "pending", "expected_amount": 200_000.0},
    {"fixed_expense": {"name": "Internet", "category": "Servicios"}, "due_date": "2026-10-25", "due_this_month": True,
     "status": "paid", "expected_amount": 25_000.0},
    {"fixed_expense": {"name": "Seguro", "category": "Seguros"}, "due_date": "2026-10-15", "due_this_month": True,
     "status": "overdue", "expected_amount": 40_000.0},
    {"fixed_expense": {"name": "Préstamo A", "category": "Deuda"}, "due_date": "2026-11-10", "due_this_month": True,
     "status": "pending", "expected_amount": 50_000.0},
    {"fixed_expense": {"name": "Gimnasio", "category": "Salud"}, "due_date": "2026-11-21", "due_this_month": True,
     "status": "not_due", "expected_amount": 15_000.0},
]


def test_fixed_expenses_of_the_statement_not_paid_yet():
    is_debt = lambda row: row.get("category") == "Deuda"  # noqa: E731
    # Casa and Gimnasio (the cut day is in); Internet is paid, Seguro was due before, Préstamo A is a debt.
    assert projection.pending_fixed(FIXED, START, END, is_debt) == Decimal("215000.0")


CYCLE = {"income": 900_000.0, "expenses": 120_000.0, "debt_paid": 60_000.0}


def test_result_is_income_minus_everything_the_statement_takes():
    figures = projection.projected(CYCLE, installments=Decimal("80000"), fixed=Decimal("215000"), savings_total=40_000,
                                   dollars=Decimal("10000"), funded_elsewhere=Decimal("0"))
    assert figures["expenses"] == 120_000 + 60_000 + 80_000 + 215_000 + 40_000 + 10_000
    assert figures["result"] == figures["income"] - figures["expenses"]
    assert sum(figures["parts"].values()) == figures["expenses"]
    assert figures["dollars_unknown"] is False


def test_abonos_paid_with_money_counted_elsewhere_are_not_spent_twice():
    figures = projection.projected(CYCLE, installments=Decimal("0"), fixed=Decimal("0"), savings_total=0, dollars=Decimal("0"),
                                   funded_elsewhere=Decimal("45000"))
    assert figures["parts"]["debt_paid"] == 15_000
    assert figures["expenses"] == 120_000 + 15_000


def test_unknown_dollars_are_flagged_not_hidden():
    figures = projection.projected(CYCLE, installments=Decimal("0"), fixed=Decimal("0"), savings_total=0, dollars=None)
    assert figures["dollars_unknown"] is True


def test_nothing_left_leaves_nothing_to_spend(monkeypatch):
    from backend.ai import strategy_dashboard

    monkeypatch.setattr(strategy_dashboard, "_owner_strategy_blueprint",
                        lambda **_k: pytest.fail("no split without a result"))
    assert projection.free_share(0) == 0.0
    assert projection.free_share(-5_000) == 0.0


def test_podes_gastar_is_the_strategys_free_share_of_the_result(monkeypatch):
    from backend.ai import strategy_dashboard

    seen = {}

    def blueprint(manual_available=None, statement_base=None):
        seen["amount"] = statement_base
        return {"safe_to_spend": 25_000.0}

    monkeypatch.setattr(strategy_dashboard, "_owner_strategy_blueprint", blueprint)
    assert projection.free_share(100_000.0) == 25_000.0
    assert seen["amount"] == 100_000.0


def test_an_unavailable_strategy_states_no_figure(monkeypatch):
    from backend.ai import strategy_dashboard

    def broken(**_k):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(strategy_dashboard, "_owner_strategy_blueprint", broken)
    assert projection.free_share(100_000.0) is None


def test_hoy_keeps_the_ledger_when_the_projection_fails(monkeypatch):
    from backend.user_product import entry_currency, vip_service

    def broken(*_a, **_k):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(projection, "project", broken)
    monkeypatch.setattr(entry_currency, "account_base_currency", lambda *_a: "CRC")
    assert vip_service._owner_statement(None, "acc", "ws", {}, {}, []) is None


def test_only_the_verified_owner_gets_the_projected_statement():
    """vip_service reads the projection only under the Owner check (``owner_account_context``)."""
    import inspect

    from backend.user_product import vip_service

    source = inspect.getsource(vip_service.get_vip_command_center)
    assert "_owner_statement(conn, account_id, workspace_id, owner_cycle, owner_savings, debts) if owner else None" in source
    assert "if owner_statement is not None:" in source


class SalaryConnection:
    """Salaries this period: one "Bono" typed in the app (50 000), no salary row and no deposit."""

    def execute(self, query, params=()):
        from types import SimpleNamespace

        from backend.user_product import owner_ledger

        if query == owner_ledger.SALARY_ROWS_SQL:
            total = 0
        elif "FROM salaries" in query:
            total = 50_000
        else:
            total = 0
        return SimpleNamespace(fetchone=lambda: {"total": total}, fetchall=lambda: [])


def test_a_bonus_typed_in_the_app_is_not_swallowed_by_the_projected_salary(monkeypatch):
    from backend.user_product import owner_ledger

    monkeypatch.setattr(owner_ledger.salary_projection, "project",
                        lambda *_a: {"results": {"projected_net": 700_000}})
    salary = owner_ledger._period_salary(SalaryConnection(), "ws", START, END,
                                         {"profile": None, "deductions": [], "base_net": 700_000.0}, {"salaries"}, is_open=True)
    # The projection replaces only salary rows: the bonus stays on top of it in the period's income.
    assert salary["received"] == 0
    assert salary["salary"] == 700_000


PROFILE = {"hourly_rate": 2_000, "overtime_multiplier": 1.5}
DEDUCTIONS = [{"deduction_type": "percentage", "amount": 10.67}, {"deduction_type": "fixed", "amount": 5_000}]


def test_an_ot_hour_is_worth_its_net_pay():
    # 2 000 × 1.5 = 3 000 gross, less the 10.67 % percentage deductions (the fixed one is the base's).
    assert projection.ot_hour_net(PROFILE, DEDUCTIONS) == Decimal("2679.9000")


def test_hours_of_ot_that_cover_a_negative_statement():
    hour = projection.ot_hour_net(PROFILE, DEDUCTIONS)
    assert projection.ot_hours_to_cover(-17_000, hour) == 7  # 6.34 hours, rounded up to whole hours
    assert projection.ot_hours_to_cover(-2_679.90, hour) == 1


def test_no_hours_when_nothing_is_missing_or_the_rate_is_unknown():
    hour = projection.ot_hour_net(PROFILE, DEDUCTIONS)
    assert projection.ot_hours_to_cover(0, hour) is None
    assert projection.ot_hours_to_cover(5_000, hour) is None
    assert projection.ot_hour_net(None, DEDUCTIONS) is None
    assert projection.ot_hours_to_cover(-17_000, None) is None


def test_the_owners_monthly_margin_is_the_statement_result():
    """Proyecciones and the debt planner read the same surplus as Hoy and the plan of the month."""
    import inspect

    from backend.user_product import vip_service

    source = inspect.getsource(vip_service.get_vip_command_center)
    assert 'if owner_statement is not None:\n        # The Owner\'s month is Hoy\'s statement counted whole' in source
    assert 'margin = owner_statement["result"]' in source
