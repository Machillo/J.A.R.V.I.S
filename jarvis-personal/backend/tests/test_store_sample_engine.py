"""The store screenshots show what the real backend computes (store-assets/, PR #289).

The native apps' STORE fixture (native/android/core/data/src/main/resources/store-sample.json)
holds an invented account (`inputs`, written by the Android StoreGoldenTest from StoreSample.kt)
and the responses the backend gives for it (`engine`). This test runs the backend's own engines
on those inputs -- basic and VIP strategy, VIP command center, guided budget, Free dashboard -- through a fake,
in-memory connection that answers the same SQL the services send, and checks that `engine` is
exactly their output. So a store image can never show a split, a priority or a sentence the
backend would not produce. No database, network or AI is involved; nothing is written.

Regenerate after changing StoreSample.kt or an engine (from jarvis-personal):
    DINCR_UPDATE_STORE_GOLDEN=1 python -m pytest backend/tests/test_store_sample_engine.py
"""
from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from backend.core.i18n import use_language
from backend.user_product import basic_service, free_service, service, vip_service
from backend.user_product.strategy_engine import build_basic_strategy, build_paycheck_plan, build_vip_insights, build_vip_strategy

GOLDEN = Path(__file__).resolve().parents[2] / "native/android/core/data/src/main/resources/store-sample.json"


def _day(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _StoreConnection:
    """Answers the queries of vip_service.get_vip_command_center and basic_service.get_guided_budget."""

    def __init__(self, inputs: dict):
        self.inputs = inputs
        self.movements = [{**m, "date": _day(m["transaction_date"])} for m in inputs["movements"]]

    def _columns(self, sql: str) -> list[str]:
        select = re.search(r"SELECT(.*?)FROM", sql, re.S).group(1)
        return [part.strip().split()[-1] for part in select.split(",")]

    def _sum(self, kind: str, start: date, end: date, category: str | None = None) -> float:
        return round(sum(float(m["amount"]) for m in self.movements
                         if m["transaction_type"] == kind and start <= m["date"] < end and (category is None or m.get("category") == category)), 2)

    def execute(self, sql: str, params=()):
        profile = self.inputs["profile"]
        if "FROM financial_profiles" in sql:
            return _Rows([{column: profile.get(column) for column in self._columns(sql)}])
        if "SUM(remaining_amount)" in sql:
            return _Rows([{"balance": sum(float(d["remaining_amount"]) for d in self.inputs["debts"])}])
        if "SUM(monthly_payment)" in sql:
            return _Rows([{"total": sum(float(d["monthly_payment"]) for d in self.inputs["debts"])}])
        if "FROM debts" in sql:
            return _Rows([{**d, "interest_rate": d.get("interest_rate") or None, "next_payment_date": _day(d.get("next_payment_date"))} for d in self.inputs["debts"]])
        if "FROM financial_goals" in sql:
            return _Rows([{"id": g["id"], "name": g["name"], "target_amount": g["target_amount"], "current_amount": g["current_amount"],
                           "target_date": _day(g.get("target_date")), "priority": g.get("priority")} for g in self.inputs["goals"]])
        if "AS debt_paid" in sql:  # _ledger_totals(conn, workspace, start, end)
            start, end = params[1], params[2]
            return _Rows([{"income": self._sum("income", start, end), "expenses": self._sum("expense", start, end), "debt_paid": 0}])
        if "source IN" in sql:  # imported (bank email) income: the STORE account has none
            return _Rows([])
        if "FROM finva_recurring_items" in sql:
            return _Rows([dict(r) for r in self.inputs["recurring"]])
        if "regexp_replace" in sql:  # recurring merchants detected in the last months
            since = params[1]
            merchants: dict[str, list] = {}
            for m in self.movements:
                if m["transaction_type"] == "expense" and m["date"] >= since and m.get("description"):
                    merchant = re.sub(r"[^a-z0-9]+", " ", m["description"].lower())[:60]
                    merchants.setdefault(merchant, []).append(m)
            rows = []
            for merchant, items in merchants.items():
                months = {(i["date"].year, i["date"].month) for i in items}
                if len(months) >= 2:
                    amounts = [float(i["amount"]) for i in items]
                    rows.append({"merchant": merchant, "average_amount": round(sum(amounts) / len(amounts), 2),
                                 "minimum_amount": min(amounts), "maximum_amount": max(amounts), "months_seen": len(months)})
            rows.sort(key=lambda r: (-r["months_seen"], -r["average_amount"]))
            return _Rows(rows[:12])
        if "FROM finva_email_candidates" in sql:
            return _Rows([{"status": "pending", "total": self.inputs["pending_notices"]}])
        if "FROM finva_budget_items" in sql:
            return _Rows([{"category": b["category"], "monthly_limit": b["monthly_limit"], "is_system": False} for b in self.inputs["budget_items"]])
        if "GROUP BY category" in sql:  # this month's spending per category (guided budget, Free dashboard)
            start, end = params[1], params[2]
            categories = sorted({m["category"] for m in self.movements if m["transaction_type"] == "expense" and start <= m["date"] < end})
            rows = [{"category": c, "amount": self._sum("expense", start, end, c)} for c in categories]
            if "ORDER BY amount DESC" in sql:
                rows.sort(key=lambda r: -r["amount"])
            return _Rows(rows)
        raise AssertionError(f"unexpected query in the STORE harness: {sql[:80]}")


def _snapshot(inputs: dict) -> dict:
    """What service._strategy_snapshot reads for this account."""
    profile = inputs["profile"]
    order = {"high": 0, "medium": 1, "low": 2}
    return {
        "monthly_income_estimate": service._monthly_income_estimate(profile),
        "essential_monthly_expenses": profile.get("essential_monthly_expenses"),
        "liquid_savings": profile.get("liquid_savings"),
        "emergency_fund_target": profile.get("emergency_fund_target"),
        "strategy_preference": None, "discretionary_monthly_minimum": None,
        "pay_frequency": profile.get("pay_frequency"), "payday_note": None,
        "debts": [{"id": d["id"], "name": d["name"], "remaining_amount": d["remaining_amount"], "monthly_payment": d["monthly_payment"],
                   "interest_rate": d.get("interest_rate") or None, "payment_day": d.get("payment_day")} for d in inputs["debts"]],
        "goals": sorted(({"id": g["id"], "name": g["name"], "target_amount": g["target_amount"], "current_amount": g["current_amount"],
                          "target_date": _day(g.get("target_date")), "priority": g.get("priority")} for g in inputs["goals"]),
                        key=lambda g: (order.get(g["priority"], 9), g["target_date"] or date.max, g["id"])),
    }


def _engine(inputs: dict, monkeypatch) -> dict:
    today = date.fromisoformat(inputs["today"])

    class _Today(date):
        @classmethod
        def today(cls):
            return today

    connection = _StoreConnection(inputs)

    @contextmanager
    def _connect():
        yield connection

    for module in (vip_service, basic_service, free_service):
        monkeypatch.setattr(module, "date", _Today)
        monkeypatch.setattr(module, "get_connection", _connect)
        monkeypatch.setattr(module, "get_current_account_id", lambda: "store-account", raising=False)
        monkeypatch.setattr(module, "get_current_workspace_id", lambda: "store-workspace")
        monkeypatch.setattr(module, "_basic_tables_ready", lambda conn, *tables: True, raising=False)
    monkeypatch.setattr(vip_service, "_table_exists", lambda conn, table: table == "finva_email_candidates")

    snapshot = _snapshot(inputs)
    basic = build_basic_strategy(snapshot)
    vip = build_vip_strategy(snapshot)
    return {  # the same composition as service.get_strategy_basic / get_strategy_vip
        "strategy_basic": {**basic, "next_paycheck": build_paycheck_plan(basic, snapshot.get("pay_frequency"), vip=False)},
        "strategy_vip": {**vip, "insights": build_vip_insights(snapshot, vip), "next_paycheck": build_paycheck_plan(vip, snapshot.get("pay_frequency"), vip=True)},
        "command_center": vip_service.get_vip_command_center(),
        "budget": basic_service.get_guided_budget(),
        "free_dashboard": free_service.get_free_dashboard(),
    }


def _plain(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def test_store_screenshots_show_the_backend_engines_output(monkeypatch):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    computed = {}
    for language in ("es", "en"):
        with use_language(language):
            computed[language] = _plain(_engine(golden[language]["inputs"], monkeypatch))
    if os.environ.get("DINCR_UPDATE_STORE_GOLDEN") == "1":
        for language, engine in computed.items():
            golden[language]["engine"] = engine
        GOLDEN.write_text(json.dumps(golden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return
    for language, engine in computed.items():
        assert golden[language].get("engine") == engine, f"store-sample.json ({language}) differs from the backend engines: regenerate it"


def test_store_sample_numbers_agree():
    """The same account in both languages: only words differ, never amounts or dates."""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    es, en = golden["es"]["inputs"], golden["en"]["inputs"]
    for key in ("movements", "debts", "goals", "recurring", "budget_items"):
        amounts = lambda rows: [(r.get("amount"), r.get("remaining_amount"), r.get("target_amount"), r.get("monthly_limit"), r.get("transaction_date")) for r in rows]
        assert amounts(es[key]) == amounts(en[key]), key
    assert es["profile"] == en["profile"]
