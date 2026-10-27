"""UNKNOWN ≠ 0 in the monthly summary (Movimientos → Análisis → Resumen del mes, every plan).

Savings nobody declared used to read ₡0 ("Ahorrado ₡0"), and an account without goals reported a
goal progress of 0 % (0 / 0). Both are unknown now (null); a declared 0 of savings stays ₡0, and
with goals the progress is the same as before. Synthetic data.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.user_product import free_service


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, profile, goals):
        self.profile, self.goals = profile, goals

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=()):
        if "FROM financial_goals" in query:
            return _Rows([self.goals])
        if "FROM financial_profiles" in query:
            return _Rows([self.profile] if self.profile is not None else [])
        raise AssertionError(query[:80])


def _summary(monkeypatch, *, profile, goals):
    monkeypatch.setattr(free_service, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(free_service, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(free_service, "get_connection", lambda: _Conn(profile, goals))
    monkeypatch.setattr(free_service, "_period_totals", lambda *_a: {"income": 500000.0, "expenses": 200000.0, "debt_paid": 0.0})
    monkeypatch.setattr(free_service, "_categories", lambda *_a: [])
    monkeypatch.setattr(free_service, "_month", lambda _period: date(2026, 10, 1))
    return free_service.get_free_monthly_summary("2026-10")


NO_GOALS = {"current": 0, "target": 0}


@pytest.mark.parametrize("profile", [None, {"liquid_savings": None}])
def test_savings_nobody_declared_are_unknown_not_zero(monkeypatch, profile):
    assert _summary(monkeypatch, profile=profile, goals=NO_GOALS)["savings"] is None


def test_declared_savings_zero_included_are_shown(monkeypatch):
    assert _summary(monkeypatch, profile={"liquid_savings": 0}, goals=NO_GOALS)["savings"] == 0
    assert _summary(monkeypatch, profile={"liquid_savings": 350000}, goals=NO_GOALS)["savings"] == 350000


def test_without_goals_there_is_no_progress_not_zero_percent(monkeypatch):
    assert _summary(monkeypatch, profile=None, goals=NO_GOALS)["goals"]["progress"] is None


def test_with_goals_the_progress_is_the_same_as_before(monkeypatch):
    assert _summary(monkeypatch, profile=None, goals={"current": 250000, "target": 1000000})["goals"]["progress"] == 25.0
