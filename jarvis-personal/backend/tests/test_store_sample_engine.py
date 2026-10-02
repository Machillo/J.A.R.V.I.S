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

import datetime as datetime_module
import json
import os
import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from backend.auth.current_user import reset_current_user, set_current_user
from backend.core.i18n import use_language
from backend.user_product import basic_service, free_service, income_policy, service, strategy_engine, vip_service

GOLDEN = Path(__file__).resolve().parents[2] / "native/android/core/data/src/main/resources/store-sample.json"
# The iOS app bundles a byte copy (DincrKit resource): written with the Android file, checked equal.
IOS_GOLDEN = Path(__file__).resolve().parents[2] / "native/ios/DincrKit/Sources/DincrCore/Resources/store-sample.json"


class _FixtureDate(date):
    """`date` with the fixture's today. Every date the harness hands the services is one of these, so
    their `isinstance(x, date)` checks (date = this class while patched) see what production sees."""
    current: date = date.min

    @classmethod
    def today(cls):
        return cls(cls.current.year, cls.current.month, cls.current.day)


def _day(value):
    return _FixtureDate.fromisoformat(value) if isinstance(value, str) else value


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _StoreConnection:
    """Answers the queries of the strategy service, the VIP command center, the guided budget and the Free dashboard."""

    def __init__(self, inputs: dict):
        self.inputs = inputs
        self.movements = [{**m, "date": _day(m["transaction_date"])} for m in inputs["movements"]]

    def _columns(self, sql: str) -> list[str]:
        select = re.sub(r"\([^()]*\)", "", re.search(r"SELECT(.*?)FROM", sql, re.S).group(1))  # NULLIF(a,0) AS a -> a
        return [part.strip().split()[-1] for part in select.split(",")]

    FILTERS = {  # the WHERE conditions the harness applies to debts/goals rows; any other one is refused
        "workspace_id=%s": lambda row: True,  # the one STORE workspace
        "remaining_amount>0": lambda row: float(row["remaining_amount"]) > 0,
        "status='active'": lambda row: row.get("status", "active") == "active",
        "target_date IS NOT NULL": lambda row: row["target_date"] is not None,
    }

    def _select(self, sql: str, rows: list[dict]) -> _Rows:
        """The query's WHERE, then its ORDER BY (Postgres sorts `priority` as text), then the SELECTed columns."""
        where = re.search(r"WHERE (.*?)(?:ORDER BY|$)", sql, re.S).group(1)
        for condition in (part.strip() for part in where.split(" AND ")):
            if condition not in self.FILTERS:
                raise AssertionError(f"unexpected condition in the STORE harness: {condition}")
            rows = [row for row in rows if self.FILTERS[condition](row)]
        order = re.search(r"ORDER BY (.*)$", sql, re.S)
        for key in reversed([part.strip() for part in order.group(1).split(",")] if order else []):
            column = key.split()[0]
            if "NULLS LAST" in key:
                rows = sorted(rows, key=lambda r: (r[column] is None, r[column] or date.min))
            else:
                rows = sorted(rows, key=lambda r: r[column])
        return _Rows([{column: row.get(column) for column in self._columns(sql)} for row in rows])

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
            return self._select(sql, [{**d, "interest_rate": d.get("interest_rate") or None, "next_payment_date": _day(d.get("next_payment_date"))}
                                      for d in self.inputs["debts"]])
        if "FROM financial_goals" in sql:
            return self._select(sql, [{**g, "target_date": _day(g.get("target_date"))} for g in self.inputs["goals"]])
        if "AS debt_paid" in sql:  # _ledger_totals(conn, workspace, start, end)
            start, end = params[1], params[2]
            return _Rows([{"income": self._sum("income", start, end), "expenses": self._sum("expense", start, end), "debt_paid": 0}])
        if "source IN" in sql:  # imported (bank email) income: the STORE account has none
            return _Rows([])
        if "FROM finva_recurring_items" in sql:
            return _Rows([dict(r) for r in self.inputs["recurring"]])
        if "regexp_replace" in sql:  # recurring merchants detected in the last months
            # The query reads the `transactions` table only (imported/bank rows); manual entries live in
            # `salaries`/`expenses` (origin salary/expense), so they are never part of it.
            since = params[1]
            merchants: dict[str, list] = {}
            for m in self.movements:
                if m.get("origin") == "transaction" and m["transaction_type"] == "expense" and m["date"] >= since and m.get("description"):
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
            rows = [{"category": b["category"], "monthly_limit": b["monthly_limit"], "is_system": False} for b in self.inputs["budget_items"]]
            return _Rows(sorted(rows, key=lambda r: (not r["is_system"], r["category"])))  # ORDER BY is_system DESC, category
        if "GROUP BY category" in sql or "GROUP BY 1" in sql:  # this month's spending per category (guided budget, Free dashboard)
            start, end = params[1], params[2]
            categories = sorted({m["category"] for m in self.movements if m["transaction_type"] == "expense" and start <= m["date"] < end})
            rows = [{"category": c, "amount": self._sum("expense", start, end, c)} for c in categories]
            if "ORDER BY amount DESC" in sql:
                rows.sort(key=lambda r: -r["amount"])
            return _Rows(rows)
        raise AssertionError(f"unexpected query in the STORE harness: {sql[:80]}")


def _engine(inputs: dict, monkeypatch) -> dict:
    today = _day(inputs["today"])
    monkeypatch.setattr(_FixtureDate, "current", today)
    connection = _StoreConnection(inputs)

    @contextmanager
    def _connect():
        yield connection

    for module in (service, vip_service, basic_service, free_service, income_policy):
        monkeypatch.setattr(module, "date", _FixtureDate)
        monkeypatch.setattr(module, "get_connection", _connect, raising=False)
        monkeypatch.setattr(module, "get_current_account_id", lambda: "store-account", raising=False)
        monkeypatch.setattr(module, "get_current_workspace_id", lambda: "store-workspace", raising=False)
        monkeypatch.setattr(module, "_basic_tables_ready", lambda conn, *tables: True, raising=False)
    monkeypatch.setattr(vip_service, "_table_exists", lambda conn, table: table == "finva_email_candidates")
    # strategy_engine reads the clock inside _goal_monthly_need (a local `from datetime import date`):
    # give it the fixture's today, or the golden would change with the month it runs in.
    goal_monthly_need = strategy_engine._goal_monthly_need
    monkeypatch.setattr(strategy_engine, "_goal_monthly_need", lambda goal, reference_date=None: goal_monthly_need(goal, reference_date or today))

    # The plan gate is not what this test pins (the fixtures gate by plan: FakeBackend/FixtureBackend).
    monkeypatch.setattr(service, "require_feature", lambda feature: None)
    # The STORE identity, explicitly (money labels read the user's base currency), so no context
    # left by another test can change the output.
    token = set_current_user({"id": 1, "account_id": "store-account", "workspace_id": "store-workspace",
                              "role": "user", "base_currency": inputs["profile"].get("base_currency", "CRC")})
    try:
        return {  # the production entry points, through the fake connection
            "strategy_basic": service.get_strategy_basic(),
            "strategy_vip": service.get_strategy_vip(),
            "command_center": vip_service.get_vip_command_center(),
            "budget": basic_service.get_guided_budget(),
            "free_dashboard": free_service.get_free_dashboard(),
        }
    finally:
        reset_current_user(token)


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
        text = json.dumps(golden, ensure_ascii=False, indent=2) + "\n"
        GOLDEN.write_text(text, encoding="utf-8", newline="\n")
        IOS_GOLDEN.write_text(text, encoding="utf-8", newline="\n")
        return
    for language, engine in computed.items():
        assert golden[language].get("engine") == engine, f"store-sample.json ({language}) differs from the backend engines: regenerate it"
    assert IOS_GOLDEN.read_bytes() == GOLDEN.read_bytes(), "the iOS copy of store-sample.json differs from the Android one: regenerate it"


def test_the_harness_uses_the_fixture_date_everywhere(monkeypatch):
    """The emergency goal (target 2027-05-28, ₡360,000 to go) is 8 months from the fixture's
    2026-09-28 on any machine date: the date checks and the clock reads all see the fixture date."""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    class _November(date):  # the machine's clock in another month
        @classmethod
        def today(cls):
            return cls(2026, 11, 15)

    monkeypatch.setattr(datetime_module, "date", _November)  # what `from datetime import date` inside a function gets
    with use_language("es"):
        engine = _plain(_engine(golden["es"]["inputs"], monkeypatch))
    assert engine == golden["es"]["engine"], "the engines' output depends on the machine's date"
    goal = engine["command_center"]["goals"][0]
    assert (goal["months_left"], goal["monthly_required"], goal["viable"]) == (8, 45000.0, True)
    assert engine["strategy_vip"]["insights"]["goal_guidance"][0]["monthly_needed"] == 45000.0
    assert engine["command_center"]["recurring"]["detected"] == []  # manual entries are not bank transactions
    # A new clock read in these engines must be routed to the fixture date before the golden is trusted.
    assert Path(strategy_engine.__file__).read_text(encoding="utf-8").count("date.today()") == 1
    for module in (service, vip_service, basic_service, free_service, income_policy):
        assert "datetime.now()" not in Path(module.__file__).read_text(encoding="utf-8"), module.__name__


def test_store_sample_numbers_agree():
    """The same account in both languages: only words differ, never amounts or dates."""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    es, en = golden["es"]["inputs"], golden["en"]["inputs"]
    for key in ("movements", "debts", "goals", "recurring", "budget_items"):
        amounts = lambda rows: [(r.get("amount"), r.get("remaining_amount"), r.get("target_amount"), r.get("monthly_limit"), r.get("transaction_date")) for r in rows]
        assert amounts(es[key]) == amounts(en[key]), key
    assert es["profile"] == en["profile"]
