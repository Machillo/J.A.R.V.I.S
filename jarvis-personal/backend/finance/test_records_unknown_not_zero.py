"""JARVIS → Registros reads (Owner): the timeline and the reconciliation never show unknown as ₡0.

- Timeline: no projected salary adds no "Ingreso de salario ₡0" event; it says so instead.
- Reconciliation: an account whose balance DINCR does not track (detected from mail, kept out of
  the net worth) is not compared as a ₡0 balance; confirming an unknown account is a 404.
Synthetic data only; no database.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.finance import reconciliation, timeline


def _timeline(monkeypatch, projected_net):
    monkeypatch.setattr(timeline, "list_account_balances", lambda: {"items": [
        {"balance_crc": 100_000, "include_in_net_worth": True, "account_type": "checking"}]})
    monkeypatch.setattr(timeline, "calculate_monthly_salary_projection", lambda: {"results": {"projected_net": projected_net}})
    monkeypatch.setattr(timeline, "get_pay_schedule", lambda: {"pay_frequency": "monthly", "pay_day": 28})
    monkeypatch.setattr(timeline, "_events_for_pay_schedule", lambda _s, start, _e, _a: [start])
    monkeypatch.setattr(timeline, "get_debts", lambda: [])
    monkeypatch.setattr(timeline, "list_fixed_expenses", lambda active_only=True: [])
    monkeypatch.setattr(timeline, "get_financial_goals", lambda: [])
    return timeline.get_financial_timeline(days=30)


def test_no_projected_salary_adds_no_zero_deposit(monkeypatch):
    report = _timeline(monkeypatch, None)
    assert [e for e in report["events"] if e["kind"] == "income"] == []
    assert report["ending_available"] == 100_000
    assert any("No hay proyección de salario" in note for note in report["assumptions"])


def test_a_projected_salary_is_still_projected(monkeypatch):
    report = _timeline(monkeypatch, 900_000)
    incomes = [e for e in report["events"] if e["kind"] == "income"]
    assert incomes and incomes[0]["amount"] == 900_000
    assert not any("No hay proyección de salario" in note for note in report["assumptions"])


class _Db:
    def __init__(self, row=None):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: self.row)

    def commit(self):
        raise AssertionError("not expected")


def test_untracked_accounts_are_not_compared_as_zero(monkeypatch):
    monkeypatch.setattr(reconciliation, "get_current_workspace_id", lambda: "workspace-x")
    monkeypatch.setattr(reconciliation, "get_connection", lambda: _Db())
    monkeypatch.setattr(reconciliation, "list_account_balances", lambda: {"items": [
        {"id": 1, "account_name": "Cuenta declarada", "include_in_net_worth": True, "current_balance": 50_000, "calculated_balance": 45_000},
        {"id": 2, "account_name": "Detectada por correo", "include_in_net_worth": False, "current_balance": 0, "calculated_balance": -12_000},
        {"id": 3, "account_name": "Inversión", "account_type": "investment", "include_in_net_worth": True}]})
    report = reconciliation.get_financial_reconciliation()
    assert [a["account_id"] for a in report["accounts"]] == [1]
    assert report["accounts"][0]["difference"] == 5_000
    assert report["summary"]["untracked_accounts"] == 1


def test_confirming_an_unknown_account_is_not_found(monkeypatch):
    monkeypatch.setattr(reconciliation, "get_current_workspace_id", lambda: "workspace-x")
    monkeypatch.setattr(reconciliation, "get_connection", lambda: _Db(row=None))
    with pytest.raises(HTTPException) as error:
        reconciliation.confirm_account_reconciliation(99, 1_000)
    assert error.value.status_code == 404
