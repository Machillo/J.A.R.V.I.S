"""The Owner's monthly ledger (Owner audit, Fase 1 §2): one rule per movement type, the same
figures on every Owner screen, nothing counted twice. Free, Basic and VIP keep their totals.

Pure rules first (synthetic amounts), then how the Owner screens use them: Movimientos list,
Resumen del mes, Hoy's monthly report and JARVIS > Análisis financiero.
"""
from types import SimpleNamespace

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import owner_ledger, summary_breakdown
from backend.user_product.owner_ledger import (
    DEBT_PAYMENTS, EXPENSES, INCOME, NOT_COUNTED, OTHER_INFLOWS, PAYROLL_ACCRUED, REFUNDS, UNCLASSIFIED, concept_of,
    month_totals,
)


def totals(*rows, **legacy):
    """rows = (transaction_type, amount); each row is one movement."""
    groups = {}
    for kind, amount in rows:
        total, count = groups.get(kind, (0, 0))
        groups[kind] = (total + amount, count + 1)
    return month_totals([(kind, total, count) for kind, (total, count) in groups.items()], **legacy)


# 1. One concept per type (spec §2.1)

@pytest.mark.parametrize("kind,concept", [
    ("income", INCOME), ("expense", EXPENSES), ("refund", REFUNDS), ("debt_payment", DEBT_PAYMENTS),
    ("loan_received", OTHER_INFLOWS), ("loan_disbursement", OTHER_INFLOWS), ("receivable_payment", OTHER_INFLOWS),
    ("asset_sale", OTHER_INFLOWS), ("receivable_offset", NOT_COUNTED), ("internal_transfer", NOT_COUNTED),
    ("transfer", UNCLASSIFIED), (" Expense ", EXPENSES),
])
def test_each_type_has_one_concept(kind, concept):
    assert concept_of(kind) == concept


@pytest.mark.parametrize("kind", ["reimbursement", "investment_withdrawal", "card_payment", "", None, "otro"])
def test_a_type_the_spec_does_not_decide_is_unclassified_never_guessed(kind):
    # Blocked by design (spec §2.4): an undecided type is visible and counted nowhere.
    assert concept_of(kind) == UNCLASSIFIED
    result = totals((kind, 500))
    assert (result["income"], result["expenses"], result["other_inflows"], result["debt_paid"]) == (0, 0, 0, 0)
    assert result["unclassified_count"] == 1


# 2. The month's figures (spec §2.1 "Cifras del mes")

def test_a_loan_received_is_money_in_but_never_income():
    result = totals(("income", 1000), ("loan_received", 500), ("expense", 400))
    assert result["income"] == 1000 and result["other_inflows"] == 500
    assert result["balance"] == 600 and result["cash_flow"] == 1100


def test_collections_and_asset_sales_are_not_income():
    result = totals(("income", 1000), ("receivable_payment", 200), ("asset_sale", 300))
    assert result["income"] == 1000 and result["other_inflows"] == 500


def test_an_offset_moves_no_money():
    result = totals(("receivable_offset", 150))
    assert (result["income"], result["expenses"], result["other_inflows"], result["balance"]) == (0, 0, 0, 0)


def test_a_refund_reduces_spending_and_is_never_income():
    result = totals(("expense", 400), ("refund", 100))
    assert result["expenses"] == 300 and result["gross_expenses"] == 400 and result["refunds"] == 100
    assert result["income"] == 0


def test_a_refund_larger_than_the_month_spending_floors_at_zero():
    result = totals(("expense", 50), ("refund", 80))
    assert result["expenses"] == 0 and result["unmatched_refunds"] == 30


def test_a_debt_payment_is_its_own_line_and_lowers_the_result():
    result = totals(("income", 1000), ("expense", 400), ("debt_payment", 300))
    assert result["expenses"] == 400 and result["debt_paid"] == 300 and result["balance"] == 300


def test_transfers_never_count_and_an_unclassified_one_is_reported():
    result = totals(("internal_transfer", 500), ("transfer", 200))
    assert (result["income"], result["expenses"], result["balance"]) == (0, 0, 0)
    assert result["unclassified_count"] == 1


def test_income_is_money_received_payroll_and_bonuses_are_gross_and_apart():
    # Overtime, VGH (negative) and bonuses are gross payroll amounts (the salary projection takes
    # CCSS and income tax from them); the money arrives inside the salary deposit. Counting both
    # would double the deposit, so they are reported apart and never added to income or the result.
    result = totals(("income", 100), ("expense", 40), salaries=1000, overtime=50, vgh=-20, bonuses=250, expenses_table=60)
    assert result["income"] == 1100 and result["expenses"] == 100 and result["balance"] == 1000
    assert result["payroll_accrued"] == {"overtime_gross": 50, "vgh_gross": -20, "bonuses_gross": 250, "total_gross": 280}


def test_payroll_accrued_without_a_deposit_marks_the_month_incomplete():
    result = totals(overtime=80)
    assert result["income"] == 0 and result["complete"] is False
    assert result["incomplete_reasons"] == ["payroll_without_deposit"]


def test_a_month_with_its_deposit_and_nothing_pending_is_complete():
    result = totals(("income", 1000), overtime=80)
    assert result["complete"] is True and result["incomplete_reasons"] == []


def test_pending_mail_and_unclassified_movements_mark_the_month_incomplete():
    result = totals(("income", 1000), ("transfer", 5), pending_mail=3)
    assert result["complete"] is False
    assert result["incomplete_reasons"] == ["pending_mail_review", "unclassified_movements"]
    assert result["pending_mail_count"] == 3


def test_other_inflows_keep_their_breakdown():
    result = totals(("loan_received", 500), ("loan_disbursement", 100), ("receivable_payment", 200), ("asset_sale", 50))
    assert (result["loan_received"], result["receivable_payments"], result["asset_sale_proceeds"]) == (600, 200, 50)
    assert result["other_inflows"] == 850 and result["income"] == 0


def test_nothing_is_counted_twice_across_concepts():
    rows = [("income", 1000), ("expense", 400), ("refund", 100), ("debt_payment", 300), ("loan_received", 500),
            ("receivable_payment", 200), ("asset_sale", 50), ("receivable_offset", 70), ("internal_transfer", 900),
            ("transfer", 60)]
    result = totals(*rows)
    counted = result["income"] + result["gross_expenses"] + result["refunds"] + result["debt_paid"] + result["other_inflows"]
    # Every movement lands in exactly one counted concept, or in none when it moves no money / is unclassified.
    assert counted == 1000 + 400 + 100 + 300 + 500 + 200 + 50
    assert result["balance"] == 1000 - 300 - 300 and result["cash_flow"] == result["balance"] + 750


# 3. Movimientos: each row says what it is (Owner only)

ROWS = [
    {"movement_id": "salary:1", "origin": "salary", "transaction_type": "income", "ledger_type": "income", "amount": 1000},
    {"movement_id": "payroll:2", "origin": "payroll", "transaction_type": "income", "ledger_type": "payroll_accrued", "amount": 50},
    {"movement_id": "expense:3", "origin": "expense", "transaction_type": "expense", "ledger_type": "expense", "amount": 60},
    {"movement_id": "transaction:4", "origin": "transaction", "transaction_type": "expense", "ledger_type": "loan_received", "amount": 500},
    {"movement_id": "transaction:5", "origin": "transaction", "transaction_type": "expense", "ledger_type": "refund", "amount": 100},
    {"movement_id": "transaction:6", "origin": "transaction", "transaction_type": "expense", "ledger_type": "debt_payment", "amount": 300},
    {"movement_id": "transaction:7", "origin": "transaction", "transaction_type": "expense", "ledger_type": "transfer", "amount": 200},
    {"movement_id": "transaction:8", "origin": "transaction", "transaction_type": "expense", "ledger_type": "expense", "amount": 400},
    {"movement_id": "transaction:9", "origin": "transaction", "transaction_type": "expense", "ledger_type": "receivable_offset", "amount": 70},
]


class ListConnection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        assert "ledger_type" in query, "the list must read each row's real type"
        return SimpleNamespace(fetchall=lambda: [dict(row) for row in self.rows])


def _as(role):
    return set_current_user({"id": 7, "account_id": "account-a", "workspace_id": "workspace-a", "role": role})


@pytest.fixture(autouse=True)
def verified_owner(monkeypatch):
    """owner_account_context() checks the stored Owner identity; here the session role stands in for it."""
    from backend.auth.current_user import get_current_user
    from backend.user_product import free_service, vip_service
    check = lambda _conn, _account, _workspace: get_current_user().get("role") == "owner"
    monkeypatch.setattr(free_service, "owner_account_context", check)
    monkeypatch.setattr(vip_service, "owner_account_context", check)


def _list_as(role, monkeypatch):
    from backend.user_product import free_service
    monkeypatch.setattr(free_service, "get_connection", lambda: ListConnection(ROWS))
    token = _as(role)
    try:
        return free_service.list_free_movements()
    finally:
        reset_current_user(token)


def test_owner_rows_carry_their_real_kind_and_what_they_count_in(monkeypatch):
    rows = {row["movement_id"]: row for row in _list_as("owner", monkeypatch)}
    assert (rows["transaction:4"]["movement_kind"], rows["transaction:4"]["counts_in"]) == ("loan_received", OTHER_INFLOWS)
    assert rows["transaction:5"]["counts_in"] == REFUNDS
    assert rows["transaction:6"]["counts_in"] == DEBT_PAYMENTS
    assert rows["transaction:7"]["counts_in"] == UNCLASSIFIED
    assert rows["transaction:9"]["counts_in"] == NOT_COUNTED
    assert rows["salary:1"]["counts_in"] == INCOME and rows["expense:3"]["counts_in"] == EXPENSES
    assert (rows["payroll:2"]["movement_kind"], rows["payroll:2"]["counts_in"]) == ("payroll_accrued", PAYROLL_ACCRUED)
    # Installed apps decode transaction_type as income/expense only: it never changes.
    assert {row["transaction_type"] for row in rows.values()} <= {"income", "expense"}
    assert all("ledger_type" not in row for row in rows.values())


@pytest.mark.parametrize("role", ["user", "admin"])
def test_free_basic_and_vip_rows_are_unchanged(role, monkeypatch):
    rows = _list_as(role, monkeypatch)
    assert all("movement_kind" not in row and "counts_in" not in row and "ledger_type" not in row for row in rows)
    assert [row["transaction_type"] for row in rows] == [row["transaction_type"] for row in ROWS]


def test_the_owner_list_adds_up_to_the_month_figures(monkeypatch):
    rows = _list_as("owner", monkeypatch)
    by_concept = {}
    for row in rows:
        by_concept[row["counts_in"]] = by_concept.get(row["counts_in"], 0) + row["amount"]
    result = totals(*[(row["ledger_type"], row["amount"]) for row in ROWS if row["origin"] == "transaction"],
                    salaries=1000, overtime=50, expenses_table=60)
    assert by_concept[INCOME] == result["income"]
    assert by_concept[PAYROLL_ACCRUED] == result["payroll_accrued"]["overtime_gross"]
    assert by_concept[EXPENSES] - by_concept[REFUNDS] == result["expenses"]
    assert by_concept[DEBT_PAYMENTS] == result["debt_paid"]
    assert by_concept[OTHER_INFLOWS] == result["other_inflows"]


# 4. The Owner screens read the ledger; everyone else keeps the current totals

OWNER_TOTALS = {"income": 1.0, "expenses": 2.0, "debt_paid": 3.0, "gross_expenses": 2.0, "refunds": 0.0,
                "unmatched_refunds": 0.0, "other_inflows": 0.0, "loan_received": 0.0, "receivable_payments": 0.0,
                "asset_sale_proceeds": 0.0, "balance": -4.0, "cash_flow": -4.0, "unclassified_count": 0,
                "payroll_accrued": {"overtime_gross": 7.0, "vgh_gross": 0.0, "bonuses_gross": 0.0, "total_gross": 7.0},
                "pending_mail_count": 2, "complete": False, "incomplete_reasons": ["pending_mail_review"]}
LEGACY_TOTALS = {"income": 10.0, "expenses": 20.0, "debt_paid": 30.0}


class SummaryConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        row = {"current": 0, "target": 0, "liquid_savings": None}
        return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: [])


@pytest.mark.parametrize("role,expected", [("owner", OWNER_TOTALS), ("user", LEGACY_TOTALS)])
def test_resumen_del_mes_uses_the_ledger_only_for_the_owner(role, expected, monkeypatch):
    from backend.user_product import free_service
    monkeypatch.setattr(free_service, "get_connection", SummaryConnection)
    monkeypatch.setattr(free_service, "_period_totals", lambda *_a: dict(LEGACY_TOTALS))
    monkeypatch.setattr(free_service, "_categories", lambda *_a: [])
    monkeypatch.setattr(owner_ledger, "owner_month_totals", lambda *_a: dict(OWNER_TOTALS))
    monkeypatch.setattr(summary_breakdown, "income_categories", lambda *_a, **_k: [])
    monkeypatch.setattr(summary_breakdown, "saved", lambda *_a: {"total": 0.0, "goals": 0.0, "salvavidas": 0.0})
    token = _as(role)
    try:
        summary = free_service.get_free_monthly_summary("2026-10")
    finally:
        reset_current_user(token)
    assert (summary["income"], summary["expenses"], summary["debt_paid"]) == (expected["income"], expected["expenses"], expected["debt_paid"])
    assert summary["balance"] == round(expected["income"] - expected["expenses"] - expected["debt_paid"], 2)


def test_hoy_reports_use_the_ledger_while_the_income_policy_keeps_its_history(monkeypatch):
    from datetime import date
    from backend.user_product import vip_service
    monkeypatch.setattr(owner_ledger, "owner_month_totals", lambda *_a: dict(OWNER_TOTALS))
    history = [{"month": "2026-09", **LEGACY_TOTALS, "balance": -40.0}, {"month": "2026-10", **LEGACY_TOTALS, "balance": -40.0}]
    reports = vip_service._owner_report_months(None, "workspace-a", history)
    assert [row["month"] for row in reports] == ["2026-09", "2026-10"]
    assert reports[-1]["income"] == 1.0 and reports[-1]["balance"] == -4.0
    assert history[-1]["income"] == 10.0, "the income policy's months are not modified"
    assert date.fromisoformat(f"{reports[0]['month']}-01")


class MonthsConnection:
    def __init__(self, months):
        self.months = months

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        if "to_regclass" in query:
            return SimpleNamespace(fetchall=lambda: [{"name": name} for name in params[0]])
        assert "event_date" not in query, "no work date is invented: payroll is dated by its record"
        assert "interval '6 hours'" in query, "record timestamps are read as Costa Rica dates"
        return SimpleNamespace(fetchall=lambda: [{"month": month} for month in self.months])


def test_analisis_financiero_uses_the_ledger_for_the_owner(monkeypatch):
    from backend.transactions import analyzer
    monkeypatch.setattr(analyzer, "get_connection", lambda: MonthsConnection(["2026-09", "2026-10"]))
    monkeypatch.setattr(owner_ledger, "owner_month_totals", lambda *_a: dict(OWNER_TOTALS, other_inflows=5.0, loan_received=5.0, cash_flow=1.0))
    token = _as("owner")
    try:
        flow = analyzer.get_monthly_flow()
    finally:
        reset_current_user(token)
    assert [row["month"] for row in flow] == ["2026-09", "2026-10"]
    october = flow[-1]
    # income = earned income only; loans, collections and sales are other inflows; debt payments lower the balance.
    assert october["income"] == 1.0 and october["other_inflows"] == 5.0 and october["loan_received"] == 5.0
    assert october["monthly_balance"] == -4.0 and october["cash_flow"] == 1.0
    assert october["expenses"] == october["spending"] == october["outflow"] == 2.0
    assert october["cumulative_balance"] == -8.0
    # Gross payroll is reported apart and the month says it is not complete.
    assert october["payroll_accrued"]["overtime_gross"] == 7.0
    assert october["complete"] is False and october["incomplete_reasons"] == ["pending_mail_review"]
