"""Synthetic inputs for the P0.2 read-purity parity tests (lifecycle / deterioration / advisor).

The financial services that feed the health, lifecycle and advisor calculations are replaced
by fixed synthetic results; the calculations themselves (deterioration signals, Advisor Core,
lifecycle state, premium strategy summary) run unchanged. The same harness produced the golden
file from the code before P0.2 (`fixtures/p02_read_parity_golden.json`), so the tests compare
the read-only code against the old behavior on identical inputs. Synthetic values only.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

WORKSPACE = "00000000-0000-4000-8000-0000000000a1"
TODAY = dt.date(2026, 9, 15)

TRANSACTIONS = [
    # Three prior months of steady flow, then a current month with higher spending and debt payments.
    *[{"transaction_date": f"2026-{m:02d}-05", "amount": 900_000, "transaction_type": "income", "category": "Salario", "description": "s"} for m in (6, 7, 8, 9)],
    *[{"transaction_date": f"2026-{m:02d}-10", "amount": 400_000, "transaction_type": "expense", "category": "Comida", "description": "e"} for m in (6, 7, 8)],
    *[{"transaction_date": f"2026-{m:02d}-12", "amount": 150_000, "transaction_type": "debt_payment", "category": "Tarjeta BAC", "description": "d"} for m in (6, 7, 8)],
    {"transaction_date": "2026-09-10", "amount": 700_000, "transaction_type": "expense", "category": "Comida", "description": "e"},
    {"transaction_date": "2026-09-12", "amount": 260_000, "transaction_type": "debt_payment", "category": "Tarjeta BAC", "description": "d"},
]
ACCOUNTS = [
    {"account_name": "Cuenta A", "balance_crc": 350_000, "include_in_net_worth": True, "account_type": "checking",
     "balance_as_of": "2026-09-15T08:00:00+00:00", "source": "manual"},
    {"account_name": "Inversión", "balance_crc": 500_000, "include_in_net_worth": True, "account_type": "investment",
     "balance_as_of": "2026-09-15T08:00:00+00:00", "source": "manual"},
]
DEBTS = [
    {"id": 1, "name": "Tarjeta sintética", "remaining_amount": 1_200_000, "monthly_payment": 150_000, "interest_rate": 36, "debt_type": "credit_card"},
    {"id": 2, "name": "Préstamo sintético", "remaining_amount": 0, "monthly_payment": 0, "interest_rate": 12, "debt_type": "loan"},
]
FIXED = [{"expected_amount": 120_000, "frequency": "monthly", "interval_months": None},
         {"expected_amount": 300_000, "frequency": "yearly", "interval_months": None}]
SALVAVIDAS = {"coverage_months": 0.8, "monthly_base": 450_000, "current_amount": 360_000, "target_months": 6}
PREVIOUS_SNAPSHOT = {"snapshot_date": dt.date(2026, 9, 14), "liquidity": 500_000, "recurring_monthly": 100_000,
                     "debt_balance": 1_000_000, "debt_monthly": 150_000, "salvavidas_coverage": 1.2, "net_worth": 0}


class _Result:
    def __init__(self, rows=None, one=None):
        self.rows, self.one = rows or [], one

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


class FakeConnection:
    """Records every statement; answers the health and strategy reads from in-memory tables."""

    def __init__(self, store: dict[str, Any]):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.store["commits"] += 1

    def rollback(self):
        pass

    def execute(self, query, params=()):
        sql = " ".join(query.split())
        self.store["statements"].append(sql)
        upper = sql.upper()
        if "FROM TRANSACTIONS" in upper:
            return _Result(rows=[dict(row) for row in TRANSACTIONS])
        if "FROM FINANCIAL_HEALTH_SNAPSHOTS" in upper and upper.startswith("SELECT"):
            before = params[1]
            before = dt.date.fromisoformat(before) if isinstance(before, str) else before
            rows = sorted((row for row in self.store["health"].values() if row["snapshot_date"] < before),
                          key=lambda row: row["snapshot_date"], reverse=True)
            return _Result(one=dict(rows[0]) if rows else None)
        if upper.startswith("INSERT INTO FINANCIAL_HEALTH_SNAPSHOTS"):
            workspace, day, liquidity, recurring, debt, debt_monthly, coverage, net_worth = params
            day = dt.date.fromisoformat(day) if isinstance(day, str) else day
            self.store["health"][(workspace, day)] = {
                "snapshot_date": day, "liquidity": liquidity, "recurring_monthly": recurring, "debt_balance": debt,
                "debt_monthly": debt_monthly, "salvavidas_coverage": coverage, "net_worth": net_worth}
            return _Result()
        if "FROM ADVISOR_CURRENT_STRATEGY" in upper:
            current = self.store["current"].get(params[0])
            return _Result(one={"strategy_hash": current} if current else None)
        if upper.startswith("INSERT INTO ADVISOR_STRATEGY_HISTORY"):
            self.store["history"].append((params[0], params[2]))
            return _Result()
        if upper.startswith("INSERT INTO ADVISOR_CURRENT_STRATEGY"):
            self.store["current"][params[0]] = params[2]
            return _Result(one={"workspace_id": params[0]})
        if upper.startswith("SELECT PG_TRY_ADVISORY_XACT_LOCK"):
            return _Result(one={"acquired": not self.store.get("run_locked")})
        if upper.startswith("SELECT PG_ADVISORY_XACT_LOCK"):
            return _Result(one={"pg_advisory_xact_lock": ""})
        raise AssertionError(f"unexpected SQL in the parity harness: {sql[:80]}")


def new_store(previous: bool = True) -> dict[str, Any]:
    health = {(WORKSPACE, PREVIOUS_SNAPSHOT["snapshot_date"]): dict(PREVIOUS_SNAPSHOT)} if previous else {}
    return {"statements": [], "commits": 0, "health": health, "current": {}, "history": []}


class _FixedDate(dt.date):
    @classmethod
    def today(cls):
        return TODAY


def install(monkeypatch, store: dict[str, Any] | None, today: dt.date = TODAY, *, real_database: bool = False,
            debts: list[dict[str, Any]] | None = None, accounts: list[dict[str, Any]] | None = None) -> None:
    """Replace the input services (never the calculations) with the synthetic results.

    With `real_database`, the connection, the workspace (the request/job identity) and the
    date stay real, so persistence and history run against PostgreSQL.
    """
    from backend.advisor import core
    from backend.ai import premium_orchestrator
    from backend.finance import deterioration
    from backend.financial_lifecycle import state

    class _Today(dt.date):
        @classmethod
        def today(cls):
            return today

    if not real_database:
        connection = lambda: FakeConnection(store)  # noqa: E731
        for module in (deterioration, core, state):
            monkeypatch.setattr(module, "get_current_workspace_id", lambda: WORKSPACE, raising=False)
            monkeypatch.setattr(module, "get_connection", connection, raising=False)
        monkeypatch.setattr(deterioration, "date", _Today)
        monkeypatch.setattr(state, "date", _Today)
        if hasattr(deterioration, "costa_rica_today"):
            monkeypatch.setattr(deterioration, "costa_rica_today", lambda: today)
    debt_rows, account_rows = debts or DEBTS, accounts or ACCOUNTS
    for module in (deterioration, core, state):
        monkeypatch.setattr(module, "list_account_balances", lambda: {"items": [dict(item) for item in account_rows]}, raising=False)
        monkeypatch.setattr(module, "get_debts", lambda: [dict(item) for item in debt_rows], raising=False)
        monkeypatch.setattr(module, "get_salvavidas_state", lambda: dict(SALVAVIDAS), raising=False)
    monkeypatch.setattr(deterioration, "list_fixed_expenses", lambda active_only=True: [dict(item) for item in FIXED])
    monkeypatch.setattr(core, "tables_exist", lambda conn, tables: True)
    monkeypatch.setattr(core, "get_financial_summary", lambda: {"setup": {"has_income_profile": True}})
    monkeypatch.setattr(core, "get_financial_reconciliation", lambda: {"summary": {"needs_review": 0, "unlinked": 0}})
    monkeypatch.setattr(core, "get_financial_timeline", lambda days=45: {
        "opening_available": 350_000, "ending_available": 420_000,
        "events": [{"date": "2026-09-20", "name": "Pago tarjeta", "projected_balance": 200_000},
                   {"date": "2026-09-30", "name": "Salario", "projected_balance": 420_000}]})
    availability = {"money_really_available": 180_000}
    monkeypatch.setattr(core, "get_real_availability", lambda: dict(availability))
    monkeypatch.setattr(state, "get_real_availability", lambda: dict(availability))
    monkeypatch.setattr(core, "calculate_debt_strategies", lambda **_rates: {
        "status": "OK", "debts": [{"id": 1, "name": "Tarjeta sintética", "interest_rate": 36, "remaining_amount": 1_200_000}],
        "doctor_strange": {"strategies": {"balanced": {"order": [{"id": 1}]}}}})
    monkeypatch.setattr(core, "_fetch_active_goals", lambda workspace_id: [])
    monkeypatch.setattr(core, "calculate_goal_reserves", lambda goals: {"items": [
        {"id": 7, "name": "Meta sintética", "target_amount": 500_000, "current_amount": 100_000,
         "monthly_needed": 50_000, "priority": 1, "target_date": "2027-03-01"}]})
    monkeypatch.setattr(core, "calculate_financial_health_score", lambda: {
        "score": 61, "level": "regular", "inputs": {"debt_service_ratio": 0.18, "highest_debt_apr": 36}})
    monkeypatch.setattr(state, "get_monthly_financial_flow", lambda: {"months": [
        {"month": "2026-08", "income": 900_000, "expenses": 400_000, "debt_payments": 150_000, "net_operational": 350_000},
        {"month": "2026-09", "income": 900_000, "expenses": 700_000, "debt_payments": 260_000, "net_operational": -60_000}]})
    monkeypatch.setattr(premium_orchestrator, "build_local_strategy_blueprint", lambda: {
        "title": "Estrategia sintética", "objective": "Ordenar deuda", "priority": {"detail": "Primero liquidez"},
        "allocation_items": [{"label": "Salvavidas", "amount": 90_000}]})
    monkeypatch.setattr(premium_orchestrator, "get_financial_engine_report", lambda: {
        "health": {"score": 61}, "forecast": {"months": 3}})


def without_volatile(value: Any) -> Any:
    """Drop the wall-clock fields that differ on every call (generated_at / captured_at)."""
    if isinstance(value, dict):
        return {key: without_volatile(item) for key, item in value.items() if key not in {"generated_at", "captured_at"}}
    if isinstance(value, list):
        return [without_volatile(item) for item in value]
    return value
