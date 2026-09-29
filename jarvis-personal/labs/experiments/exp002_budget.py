"""EXPERIMENT 002: budget use and debt payoff order on synthetic data (Labs-only algorithm).

A sketch of an idea, not DINCR behaviour: nothing here is imported by the
backend, and promoting it means designing it again in a normal PR (docs/labs.md).
Decimal only.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from labs import db, runtime, seed, synthetic

CENT = Decimal("0.01")


def payoff(debts: list[dict], budget: Decimal, order: str) -> dict:
    """Months and interest to clear every debt: minimums first, the rest of `budget` to the first in `order`."""
    balances = [{"rate": Decimal(d["interest_rate"] or 0) / 12, "left": Decimal(d["remaining_amount"]),
                 "min": Decimal(d["monthly_payment"])} for d in debts]
    key = (lambda d: d["left"]) if order == "snowball" else (lambda d: -d["rate"])
    interest = Decimal(0)
    for month in range(1, 601):
        live = sorted([d for d in balances if d["left"] > 0], key=key)
        if not live:
            return {"months": month - 1, "interest": str(interest.quantize(CENT))}
        money = budget
        for debt in live:
            grown = (debt["left"] * (1 + debt["rate"])).quantize(CENT, rounding=ROUND_HALF_UP)
            interest += grown - debt["left"]
            debt["left"] = grown
        for debt in live:
            pay = min(debt["min"], debt["left"], money)
            debt["left"] -= pay
            money -= pay
        for debt in live:
            pay = min(debt["left"], money)
            debt["left"] -= pay
            money -= pay
        if money == budget:
            return {"months": None, "interest": str(interest.quantize(CENT))}  # nothing could be paid this month
    return {"months": None, "interest": str(interest.quantize(CENT))}


def run(scenario: str = "normal", seed_value: int = 7) -> dict:
    dsn = runtime.require_active()
    db.reset(dsn)
    dataset = synthetic.build(scenario, seed=seed_value)
    seed.write(dataset)
    conn = db.connect_labs()
    results = []
    try:
        with conn.cursor() as cur:
            for user in dataset.users:
                cur.execute("""SELECT b.category, b.monthly_limit,
                                      COALESCE((SELECT SUM(t.amount) FROM transactions t WHERE t.workspace_id=b.workspace_id
                                                AND t.category=b.category AND t.transaction_type='expense'
                                                AND t.transaction_date BETWEEN %s AND %s), 0) AS spent
                               FROM finva_budget_items b WHERE b.workspace_id=%s""",
                            (synthetic.TODAY.replace(day=1).isoformat(), synthetic.TODAY.isoformat(), user.workspace_id))
                budgets = [{"category": r["category"], "limit": str(r["monthly_limit"]), "spent": str(r["spent"]),
                            "exceeded": r["spent"] > r["monthly_limit"]} for r in cur.fetchall()]
                cur.execute("SELECT remaining_amount, monthly_payment, interest_rate FROM debts WHERE workspace_id=%s",
                            (user.workspace_id,))
                debts = cur.fetchall()
                budget = sum((Decimal(d["monthly_payment"]) for d in debts), Decimal(0)) * Decimal("1.25")
                results.append({"user": user.key, "plan": user.plan, "currency": user.base_currency, "budgets": budgets,
                                "payoff": {"snowball": payoff(debts, budget, "snowball"),
                                                  "avalanche": payoff(debts, budget, "avalanche")}})
    finally:
        conn.close()
    return {"scenario": scenario, "seed": seed_value, "users": results}
