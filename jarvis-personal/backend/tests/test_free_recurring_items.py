"""UX-9: every plan registers, edits and deletes its fixed/recurring commitments.

`recurring_items` (the four /user-product/basic/recurring routes) opens from Free through the
built-in plan map; the Basic intelligence around them (budget, calendar, reports, strategy) stays
Basic. Production needs no change: Free has no plan_features row for recurring_items, so access
follows the built-in map. Synthetic identities; the connection is a fake.
"""
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.auth import saas
from backend.user_product import routes


class _Conn:
    """No plan_features row (as in production for Free): the built-in map decides."""

    def __init__(self, plan):
        self.plan = plan

    def execute(self, query, params=()):
        return SimpleNamespace(fetchone=lambda: None, fetchall=lambda: [])

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _as(monkeypatch, plan, role="user"):
    monkeypatch.setattr(saas, "get_current_user", lambda: {"id": 9, "role": role})
    monkeypatch.setattr(saas, "get_current_account_id", lambda: 9)
    monkeypatch.setattr(saas, "_activate_self_service_if_ready", lambda conn, account: None)
    monkeypatch.setattr(saas, "_subscription", lambda conn, account: {"plan": plan, "status": "active", "access_source": "owner_grant"})
    monkeypatch.setattr(saas, "get_connection", lambda: _Conn(plan))


@pytest.mark.parametrize("plan", ["free", "basic", "vip"])
def test_every_plan_manages_its_recurring_commitments(monkeypatch, plan):
    _as(monkeypatch, plan)
    assert saas.require_feature("recurring_items") is True


@pytest.mark.parametrize("feature", ["guided_budget", "financial_calendar", "basic_reports", "basic_dashboard", "strategy_basic", "strategy_vip"])
def test_free_gets_no_premium_intelligence_by_accident(monkeypatch, feature):
    _as(monkeypatch, "free")
    with pytest.raises(HTTPException) as denied:
        saas.require_feature(feature)
    assert denied.value.status_code == 403


@pytest.mark.parametrize("feature", ["recurring_items", "guided_budget", "financial_calendar", "basic_reports", "strategy_vip"])
def test_the_owner_keeps_every_capability(monkeypatch, feature):
    _as(monkeypatch, "free", role="owner")
    assert saas.require_feature(feature) is True


def test_basic_and_vip_keep_their_basic_features(monkeypatch):
    for plan in ("basic", "vip"):
        _as(monkeypatch, plan)
        for feature in ("guided_budget", "financial_calendar", "basic_reports"):
            assert saas.require_feature(feature) is True


def test_create_edit_and_delete_are_gated_only_by_recurring_items():
    for handler in (routes.recurring_list, routes.recurring_create, routes.recurring_update, routes.recurring_delete):
        source = inspect.getsource(handler)
        assert 'require_feature("recurring_items")' in source and "basic" not in source.split("require_feature")[1].split(")")[0]


def test_the_plan_catalogue_lists_recurring_payments_in_free_not_as_a_basic_extra():
    assert "Pagos fijos y recurrentes" in saas.PLAN_COPY["free"]["features"]
    assert "Recurrentes" not in saas.PLAN_COPY["basic"]["features"]
    assert "Fixed and recurring payments" in saas.PLAN_COPY_EN["free"]["features"]
