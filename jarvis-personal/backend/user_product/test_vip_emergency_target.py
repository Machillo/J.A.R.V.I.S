"""The VIP command center must see the declared emergency-fund target.

Regression: the shared profile read (`basic_service._profile`) did not select
`emergency_fund_target`, so Home read it as missing → target 0 → gap 0. With savings
below the declared target and an expensive card, the director said "debt" and the
roadmap ended in "Invertir" instead of "Completar reserva" / "Esperar para invertir".

The shared in-memory ledger returns the whole profile row whatever the query selects,
which hid the bug; the connection below only returns the columns the SQL asks for.
All data is synthetic.
"""
import re

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.core.i18n import use_language
from backend.user_product import basic_service, service, vip_service
from backend.user_product.test_mail_preserves_financial_state import (
    ACCOUNT, ALLOWED_USER_ID, WORKSPACE, LedgerConnection, LedgerDB,
)

_PROFILE_READ = re.compile(r"SELECT (?P<columns>.+?) FROM financial_profiles WHERE account_id=%s AND workspace_id=%s")


class ProjectingConnection(LedgerConnection):
    """Profile reads return only the selected columns, like Postgres does."""

    def execute(self, query, params=()):
        result = super().execute(query, params)
        match = _PROFILE_READ.search(" ".join(query.split()))
        row = result.fetchone() if match else None
        if not row:
            return result
        columns = [column.strip() for column in match.group("columns").split(",")]
        return self._result(one={column: row[column] for column in columns if column in row})


class ProjectingDB(LedgerDB):
    def connect(self):
        return ProjectingConnection(self)


@pytest.fixture
def ledger(monkeypatch):
    database = ProjectingDB()
    profile = database.state["profiles"][ACCOUNT]
    # Declared reserve below its declared target, card at 30% (see _debt()).
    profile.update({"liquid_savings": 240000, "emergency_fund_target": 600000})
    for module in (vip_service, service, basic_service):
        monkeypatch.setattr(module, "get_connection", database.connect, raising=False)
    return database


def _home():
    token = set_current_user({"id": ALLOWED_USER_ID, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"})
    try:
        with use_language("es"):
            return vip_service.get_vip_command_center()
    finally:
        reset_current_user(token)


def test_profile_read_includes_the_declared_emergency_target(ledger):
    with ledger.connect() as conn:
        assert basic_service._profile(conn, ACCOUNT, WORKSPACE)["emergency_fund_target"] == 600000


def test_reserve_below_declared_target_is_the_priority_and_blocks_investing(ledger):
    center = _home()
    titles = [step["title"] for step in center["roadmap"]]
    assert center["director"]["priority"] == "emergency", titles
    assert "Completar reserva" in titles
    assert titles[-1] == "Esperar para invertir"


def test_reserve_at_its_target_keeps_the_debt_priority(ledger):
    ledger.state["profiles"][ACCOUNT]["liquid_savings"] = 600000
    center = _home()
    titles = [step["title"] for step in center["roadmap"]]
    assert center["director"]["priority"] == "debt"
    assert "Completar reserva" not in titles


def test_unknown_target_is_not_invented(ledger):
    # No declared target: no reserve step is invented from it (unknown stays unknown).
    ledger.state["profiles"][ACCOUNT]["emergency_fund_target"] = None
    assert "Completar reserva" not in [step["title"] for step in _home()["roadmap"]]


def test_home_stays_read_only(ledger):
    before = ledger.state
    _home()
    assert ledger.state == before
