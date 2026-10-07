"""UX-8: VIP onboarding never requires choosing a priority (none stored = DINCR's recommendation).

The other onboarding checks are unchanged. Synthetic identity; the connection is a recording fake.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.auth import saas
from backend.auth.models import UnifiedOnboardingRequest


class _Conn:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return SimpleNamespace(fetchone=lambda: {"account_id": 7}, fetchall=lambda: [])

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def vip(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(saas, "get_current_user", lambda: {"id": 7, "role": "user"})
    monkeypatch.setattr(saas, "get_current_account_id", lambda: 7)
    monkeypatch.setattr(saas, "get_current_workspace_id", lambda: "00000000-0000-4000-8000-0000000000b7")
    monkeypatch.setattr(saas, "_subscription", lambda _conn, _account: {"plan": "vip", "access_source": "owner_grant"})
    monkeypatch.setattr(saas, "enrich_identity", lambda user: user)
    monkeypatch.setattr(saas, "get_connection", lambda: conn)
    return conn


def _payload(**kw):
    base = dict(income_type="fixed", fixed_monthly_salary=900000, work_days_per_week=5, pay_frequency="monthly",
                essential_monthly_expenses=400000)
    return UnifiedOnboardingRequest(**{**base, **kw})


def test_vip_onboarding_needs_no_priority_and_stores_none(vip):
    assert saas.complete_onboarding(_payload())["status"] == "ok"
    insert = next(params for sql, params in vip.calls if sql.startswith("INSERT INTO financial_profiles"))
    assert insert[12] is None  # strategy_preference: DINCR's recommendation


def test_a_priority_sent_by_an_older_client_is_still_stored(vip):
    saas.complete_onboarding(_payload(strategy_preference="debt"))
    insert = next(params for sql, params in vip.calls if sql.startswith("INSERT INTO financial_profiles"))
    assert insert[12] == "debt"


def test_the_other_vip_onboarding_checks_are_unchanged(vip):
    with pytest.raises(HTTPException) as missing:
        saas.complete_onboarding(_payload(essential_monthly_expenses=None))
    assert missing.value.status_code == 422
