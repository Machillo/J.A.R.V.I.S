"""Deterministic synthetic data for DINCR Labs. Everything here is invented.

- The same (scenario, seed) always produces the same rows (``random.Random(seed)``;
  identifiers are uuid5 of the seed and a name).
- Emails use the reserved ``.invalid`` top-level domain (RFC 2606): no message
  can ever be delivered to a synthetic user.
- Every synthetic account has role ``user``. The ``owner_like_test`` plan is a
  label for experiments that need "everything unlocked"; it never grants the
  Owner role, Owner routes or Owner configuration.
- Money is Decimal, quantized to the column's scale, within the column's limit
  (labs/limits.py).
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from labs import limits

NAMESPACE = uuid.UUID("5f0d2a55-1ab5-4c1a-9d1e-00000000d1c7")  # Labs-only namespace, not a real id
PLANS = ("free", "basic", "vip", "owner_like_test")
SCENARIOS = ("empty", "normal", "heavy", "edge", "broken")
SYNTHETIC_EMAIL_DOMAIN = "labs.invalid"
TODAY = date(2026, 9, 15)  # fixed "today": seeds are reproducible regardless of the clock

CATEGORIES = ("Alimentación", "Transporte", "Servicios", "Salud", "Educación", "Entretenimiento",
              "Hogar", "Ropa", "Mascotas", "Tecnología", "Viajes", "Regalos", "Suscripciones", "Otros")
MERCHANTS = ("SUPER EJEMPLO", "GASOLINERA DEMO", "FARMACIA FICTICIA", "CAFE PRUEBA", "TIENDA LABS",
             "CINE SINTETICO", "LIBRERIA DEMO", "VETERINARIA EJEMPLO", "HOSTING EJEMPLO", "TAXI PRUEBA")


def _money(value: Decimal | float | int | str, table: str, column: str) -> Decimal:
    step = limits.step_for(table, column)
    amount = Decimal(str(value)).quantize(step, rounding=ROUND_HALF_UP)
    if abs(amount) > limits.max_for(table, column):
        raise ValueError(f"{table}.{column} value outside NUMERIC limit")
    return amount


@dataclass
class SyntheticUser:
    key: str
    plan: str
    base_currency: str
    allowed_id: int
    users_id: int
    account_id: str
    workspace_id: str
    email: str
    display_name: str
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def identity(self) -> dict[str, Any]:
        """The request identity Labs sets for this user (never role 'owner')."""
        return {"id": self.allowed_id, "email": self.email, "role": "user", "status": "active",
                "account_id": self.account_id, "workspace_id": self.workspace_id,
                "account_role": "user", "workspace_role": "owner", "base_currency": self.base_currency,
                "labs_plan": self.plan}


@dataclass
class Dataset:
    scenario: str
    seed: int
    users: list[SyntheticUser]
    invalid_rows: list[dict[str, Any]] = field(default_factory=list)  # 'broken' only: rows the DB must reject

    def counts(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for user in self.users:
            for table, rows in user.rows.items():
                totals[table] = totals.get(table, 0) + len(rows)
        return dict(sorted(totals.items()))


def _user(seed: int, index: int, key: str, plan: str, base_currency: str) -> SyntheticUser:
    if plan not in PLANS:
        raise ValueError(f"unknown plan {plan!r}")
    uid = lambda kind: str(uuid.uuid5(NAMESPACE, f"{seed}:{key}:{kind}"))  # noqa: E731
    return SyntheticUser(
        key=key, plan=plan, base_currency=base_currency,
        allowed_id=900_000 + index, users_id=950_000 + index,
        account_id=uid("account"), workspace_id=uid("workspace"),
        email=f"{key}.{seed}@{SYNTHETIC_EMAIL_DOMAIN}", display_name=f"Persona Sintética {index + 1}",
    )


def _history(user: SyntheticUser, rng: random.Random, months: int, per_month: int, *, max_amount: int = 90_000) -> None:
    txs = user.rows.setdefault("transactions", [])
    salaries = user.rows.setdefault("salaries", [])
    expenses = user.rows.setdefault("expenses", [])
    income = Decimal(rng.randrange(450_000, 2_400_000, 1000)) if user.base_currency == "CRC" else Decimal(rng.randrange(900, 4800))
    scale = Decimal(1) if user.base_currency == "CRC" else Decimal("0.002")
    for month in range(months):
        start = (TODAY.replace(day=1) - timedelta(days=31 * month)).replace(day=1)
        salaries.append({"amount": _money(income, "salaries", "amount"), "received_date": start.replace(day=min(28, 15)),
                         "source": "Salario sintético"})
        for _ in range(per_month):
            day = start + timedelta(days=rng.randrange(0, 28))
            amount = _money(Decimal(rng.randrange(500, max_amount, 5)) * scale, "transactions", "amount")
            category = rng.choice(CATEGORIES)
            txs.append({"transaction_date": day.isoformat(), "description": rng.choice(MERCHANTS),
                        "amount": amount, "transaction_type": "expense", "category": category, "source": "labs"})
            if rng.random() < 0.3:
                expenses.append({"category": category, "amount": _money(amount, "expenses", "amount"),
                                 "expense_date": day, "description": "Gasto sintético"})


def _extras(user: SyntheticUser, rng: random.Random, *, overdue_debt: bool, completed_goal: bool,
            exceeded_budget: bool) -> None:
    unit = Decimal(1) if user.base_currency == "CRC" else Decimal("0.002")
    user.rows["debts"] = [
        {"name": "Tarjeta de ejemplo", "debt_type": "credit_card",
         "total_amount": _money(Decimal(850_000) * unit, "debts", "total_amount"),
         "remaining_amount": _money(Decimal(610_000) * unit, "debts", "remaining_amount"),
         "monthly_payment": _money(Decimal(45_000) * unit, "debts", "monthly_payment"),
         "interest_rate": Decimal("0.3600"), "payment_day": 20,
         "next_payment_date": TODAY - timedelta(days=12) if overdue_debt else TODAY + timedelta(days=5)},
        {"name": "Préstamo sintético", "debt_type": "loan",
         "total_amount": _money(Decimal(3_000_000) * unit, "debts", "total_amount"),
         "remaining_amount": _money(Decimal(400_000) * unit, "debts", "remaining_amount"),
         "monthly_payment": _money(Decimal(95_000) * unit, "debts", "monthly_payment"),
         "interest_rate": Decimal("0.1450"), "payment_day": 5, "next_payment_date": TODAY + timedelta(days=20)},
    ]
    goal_target = _money(Decimal(500_000) * unit, "financial_goals", "target_amount")
    user.rows["financial_goals"] = [
        {"name": "Fondo de emergencia", "target_amount": goal_target,
         "current_amount": goal_target if completed_goal else _money(goal_target / 3, "financial_goals", "current_amount"),
         "status": "completed" if completed_goal else "active", "target_date": TODAY + timedelta(days=180)},
    ]
    month_start = TODAY.replace(day=1).isoformat()
    spent = sum((row["amount"] for row in user.rows.get("transactions", []) if row["category"] == "Alimentación"
                 and month_start <= row["transaction_date"] <= TODAY.isoformat()), Decimal(0))
    limit = _money(Decimal(50_000) * unit, "finva_budget_items", "monthly_limit")
    if exceeded_budget:  # one purchase alone passes the limit: exceeded whatever the random history holds
        user.rows.setdefault("transactions", []).append(
            {"transaction_date": TODAY.isoformat(), "description": "SUPER EJEMPLO", "category": "Alimentación",
             "amount": _money(limit + Decimal(1), "transactions", "amount"), "transaction_type": "expense", "source": "labs"})
    else:  # comfortably above what this month's history spent
        limit = _money(max(limit, spent * 2 + Decimal(1)), "finva_budget_items", "monthly_limit")
    user.rows["finva_budget_items"] = [{"category": "Alimentación", "monthly_limit": limit}]
    user.rows["finva_recurring_items"] = [
        {"name": "Internet sintético", "amount": _money(Decimal(28_900) * unit, "finva_recurring_items", "amount"),
         "kind": "expense", "day_of_month": 10},
        {"name": "Streaming demo", "amount": _money(Decimal(6_500) * unit, "finva_recurring_items", "amount"),
         "kind": "expense", "day_of_month": 2},
    ]
    user.rows["exchange_rates"] = [
        {"rate_date": TODAY - timedelta(days=d), "currency": "USD",
         "exchange_rate": _money(Decimal(505) + Decimal(rng.randrange(-300, 300)) / 100, "exchange_rates", "exchange_rate"),
         "source": "labs-synthetic"} for d in range(0, 7)
    ]
    user.rows["account_balances"] = [
        {"name": "Cuenta de ejemplo", "account_type": "checking", "currency": user.base_currency,
         "current_balance": _money(Decimal(rng.randrange(10_000, 900_000)) * unit, "account_balances", "current_balance")},
    ]


def _edge_rows(user: SyntheticUser) -> None:
    """Boundary values that must be stored exactly (no float, no silent rounding)."""
    tx_max = limits.max_for("transactions", "amount")
    user.rows["transactions"] = [
        {"transaction_date": "2026-02-28", "description": "MONTO MINIMO", "amount": Decimal("0.01"),
         "transaction_type": "expense", "category": "Otros", "source": "labs-edge"},
        {"transaction_date": "2028-02-29", "description": "DIA BISIESTO", "amount": Decimal("1.00"),
         "transaction_type": "expense", "category": "Otros", "source": "labs-edge"},
        {"transaction_date": "2026-12-31", "description": "FIN DE AÑO", "amount": Decimal("0.00"),
         "transaction_type": "expense", "category": "Otros", "source": "labs-edge"},
        {"transaction_date": "2026-01-01", "description": "MAXIMO TRANSACCION", "amount": tx_max,
         "transaction_type": "income", "category": "Otros", "source": "labs-edge"},
        {"transaction_date": "2026-09-01", "description": "USD CONVERTIDO", "amount": Decimal("10605.00"),
         "original_amount": Decimal("21.00"), "original_currency": "USD", "exchange_rate": Decimal("505.000000"),
         "transaction_type": "expense", "category": "Servicios", "source": "labs-edge"},
        {"transaction_date": "2026-09-02", "description": "COMERCIO Ñ&<>\"' EXTRAÑO", "amount": Decimal("33.33"),
         "transaction_type": "expense", "category": "Otros", "source": "labs-edge"},
    ]
    user.rows["expenses"] = [{"category": "Otros", "amount": limits.max_for("expenses", "amount"),
                              "expense_date": date(2026, 1, 1), "description": "MAXIMO GASTO"}]
    user.rows["salaries"] = [{"amount": Decimal("0.01"), "received_date": date(2026, 9, 30), "source": "MINIMO",
                              "original_amount": Decimal("0.01"), "original_currency": "USD",
                              "exchange_rate": Decimal("0.000001")}]
    user.rows["exchange_rates"] = [{"rate_date": date(2026, 9, 1), "currency": "USD",
                                    "exchange_rate": limits.max_for("exchange_rates", "exchange_rate"),
                                    "source": "labs-edge-max"}]
    user.rows["account_balances"] = [{"name": "Saldo máximo", "account_type": "savings", "currency": user.base_currency,
                                      "current_balance": limits.max_for("account_balances", "current_balance")}]


def _broken_rows() -> list[dict[str, Any]]:
    """Inputs the database must refuse. Each names what should reject it."""
    tx = {"transaction_date": "2026-09-01", "description": "INVALIDO", "transaction_type": "expense",
          "category": "Otros", "source": "labs-broken"}
    return [
        {"table": "transactions", "why": "overflow NUMERIC(12,2)", "row": {**tx, "amount": limits.overflow_for("transactions", "amount")}},
        {"table": "expenses", "why": "overflow NUMERIC(14,2)",
         "row": {"category": "Otros", "amount": limits.overflow_for("expenses", "amount")}},
        {"table": "salaries", "why": "partial original-currency triple (CHECK)",
         "row": {"amount": Decimal("100.00"), "original_amount": Decimal("1.00"), "original_currency": "USD"}},
        {"table": "salaries", "why": "unsupported original currency (CHECK)",
         "row": {"amount": Decimal("100.00"), "original_amount": Decimal("1.00"), "original_currency": "EUR",
                 "exchange_rate": Decimal("600")}},
        {"table": "exchange_rates", "why": "overflow NUMERIC(14,6)",
         "row": {"rate_date": date(2026, 9, 1), "currency": "USD",
                 "exchange_rate": limits.overflow_for("exchange_rates", "exchange_rate")}},
    ]


def build(scenario: str = "normal", seed: int = 7, *, heavy_count: int = 5000) -> Dataset:
    """Build a dataset in memory (nothing is written)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose one of {', '.join(SCENARIOS)}")
    rng = random.Random(f"{scenario}:{seed}")
    if scenario == "empty":
        return Dataset(scenario, seed, [_user(seed, 0, "vacio", "free", "CRC")])
    if scenario == "heavy":
        user = _user(seed, 0, "pesado", "vip", "CRC")
        months = 24
        _history(user, rng, months, max(1, -(-heavy_count // months)))
        _extras(user, rng, overdue_debt=False, completed_goal=False, exceeded_budget=True)
        user.rows["transactions"] = user.rows["transactions"][-heavy_count:]  # exactly heavy_count, overspend kept
        return Dataset(scenario, seed, [user])
    if scenario == "edge":
        user = _user(seed, 0, "limites", "vip", "CRC")
        _edge_rows(user)
        usd = _user(seed, 1, "limites-usd", "vip", "USD")
        _edge_rows(usd)
        return Dataset(scenario, seed, [user, usd])
    if scenario == "broken":
        return Dataset(scenario, seed, [_user(seed, 0, "roto", "free", "CRC")], invalid_rows=_broken_rows())
    users = [
        _user(seed, 0, "free", "free", "CRC"),
        _user(seed, 1, "basic", "basic", "CRC"),
        _user(seed, 2, "vip", "vip", "CRC"),
        _user(seed, 3, "vip-usd", "vip", "USD"),
        _user(seed, 4, "owner-like", "owner_like_test", "CRC"),
    ]
    for index, user in enumerate(users):
        _history(user, rng, months=3, per_month=20)
        _extras(user, rng, overdue_debt=index == 1, completed_goal=index == 2, exceeded_budget=index in {2, 3})
    return Dataset(scenario, seed, users)
