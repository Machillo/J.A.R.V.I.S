"""Users read surfaces must not write financial truth (CLAUDE.md §4.C).

Opening Home, the financial situation, the debt list or VIP Strategy must never
record payments, change debts or balances, create transactions or advance
goals. Each surface runs against a connection that fails the moment it tries to
INSERT/UPDATE/DELETE a financial table, so a hidden write inside any helper is
caught, not just the ones a regex would see.

Covered today: DINCR Users Home (VIP command center), financial situation,
debt list, strategy (VIP) and the VIP Strategy dashboard engine. The debt
installment automation behind finance.service.get_debts is covered by
finance/test_debt_reads_are_read_only.py. To cover a new read surface, add it to
READ_SURFACES with the ledger fake (extend the fake's query handlers if needed).
"""
import re

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import service, vip_service
from backend.user_product.test_income_policy import _strategy
from backend.user_product.test_mail_preserves_financial_state import ACCOUNT, WORKSPACE, LedgerDB

FINANCIAL_TABLES = {
    "transactions", "debts", "debt_payments", "account_balances", "financial_goals", "goals",
    "goal_contributions", "financial_profiles", "salaries", "savings", "recurring_income",
    "fixed_expenses", "finva_email_candidates", "financial_input_events", "payroll_salary_reports",
    "receivables", "investments",
}
WRITE = re.compile(r"^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:public\.)?([a-z_]+)", re.I)


class FinancialWrite(AssertionError):
    pass


class ReadOnlyLedger(LedgerDB):
    """The Home/Strategy ledger fake, refusing any financial write."""

    def __init__(self):
        super().__init__()
        self.writes = []

    def connect(self):
        connection = super().connect()
        execute = connection.execute

        def guarded(query, params=()):
            match = WRITE.match(query)
            if match and match.group(1).lower() in FINANCIAL_TABLES:
                self.writes.append(match.group(1))
                raise FinancialWrite(f"read surface wrote to {match.group(1)}")
            return execute(query, params)

        connection.execute = guarded
        return connection


@pytest.fixture
def ledger(monkeypatch):
    db = ReadOnlyLedger()
    for module in (vip_service, service):
        monkeypatch.setattr(module, "get_connection", db.connect)
    monkeypatch.setattr(service, "require_feature", lambda *_args, **_kwargs: None)
    token = set_current_user({"id": 41, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"})
    yield db
    reset_current_user(token)


READ_SURFACES = {
    "home_command_center": lambda _mp, _db: vip_service.get_vip_command_center(),
    "financial_situation": lambda _mp, _db: service.get_financial_situation(),
    "debt_list": lambda _mp, _db: service.list_user_debts(),
    "strategy_vip": lambda _mp, _db: service.get_strategy_vip(),
    "vip_strategy_dashboard": lambda mp, db: _strategy(mp, db),
}


@pytest.mark.parametrize("surface", sorted(READ_SURFACES))
def test_users_read_surfaces_do_not_write_financial_tables(surface, ledger, monkeypatch):
    before = ledger.state
    READ_SURFACES[surface](monkeypatch, ledger)
    READ_SURFACES[surface](monkeypatch, ledger)  # reading twice changes nothing either
    assert ledger.writes == []
    assert ledger.state == before


def test_the_guard_catches_a_hidden_write(ledger, monkeypatch):
    """Mutation check: a helper that writes during a read makes the surface fail."""
    original = vip_service.get_vip_command_center

    def home_with_hidden_write():
        with ledger.connect() as conn:
            conn.execute("UPDATE debts SET remaining_amount=0 WHERE workspace_id=%s", (WORKSPACE,))
        return original()

    monkeypatch.setattr(vip_service, "get_vip_command_center", home_with_hidden_write)
    with pytest.raises(FinancialWrite):
        READ_SURFACES["home_command_center"](monkeypatch, ledger)
