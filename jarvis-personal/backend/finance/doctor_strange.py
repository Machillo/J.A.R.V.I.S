from __future__ import annotations

import itertools
import math
from datetime import date
from typing import Any


MAX_EXHAUSTIVE_DEBTS = 8
MAX_MONTHS = 600


def _number(value: Any) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _add_months(day: date, months: int) -> date:
    absolute = day.year * 12 + day.month - 1 + months
    year, month_index = divmod(absolute, 12)
    month = month_index + 1
    month_days = (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(day.day, month_days))


def _normalized_debt(raw: dict[str, Any], index: int) -> dict[str, Any]:
    balance = _number(raw.get("remaining_amount"))
    minimum = min(_number(raw.get("monthly_payment")), balance) if balance else 0.0
    return {
        "id": raw.get("id", index + 1),
        "name": raw.get("name") or f"Deuda {index + 1}",
        "balance": balance,
        "minimum": minimum,
        "annual_rate": _number(raw.get("interest_rate")) / 100.0,
        "fixed_fee": _number(raw.get("fixed_fee_amount")),
        "prepayment_penalty_amount": _number(raw.get("prepayment_penalty_amount")),
        "prepayment_penalty_percent": _number(raw.get("prepayment_penalty_percent")) / 100.0,
        "penalty_applied": False,
    }


def simulate_order(
    debts: list[dict[str, Any]],
    order: tuple[int, ...],
    *,
    extra_payment: float = 0.0,
    start_date: date | None = None,
) -> dict[str, Any]:
    start = start_date or date.today()
    working = [_normalized_debt(item, index) for index, item in enumerate(debts)]
    monthly_budget = sum(item["minimum"] for item in working) + _number(extra_payment)
    payoff: dict[int, dict[str, Any]] = {}
    total_interest = 0.0
    total_fees = 0.0
    total_penalties = 0.0

    if not working or monthly_budget <= 0:
        return {"status": "NO_PAYMENT", "months": None, "order": [], "payoffs": []}

    for month in range(1, MAX_MONTHS + 1):
        period_start = _add_months(start, month - 1)
        period_end = _add_months(start, month)
        days = max((period_end - period_start).days, 1)
        active = [item for item in working if item["balance"] > 0.005]
        if not active:
            break

        for item in active:
            interest = item["balance"] * item["annual_rate"] * days / 365.0
            item["balance"] += interest + item["fixed_fee"]
            total_interest += interest
            total_fees += item["fixed_fee"]

        remaining_budget = monthly_budget
        for item in active:
            paid = min(item["minimum"], item["balance"], remaining_budget)
            item["balance"] -= paid
            remaining_budget -= paid

        for target_index in order:
            item = working[target_index]
            if item["balance"] <= 0.005 or remaining_budget <= 0.005:
                continue
            payoff_amount = item["balance"]
            if remaining_budget >= payoff_amount and not item["penalty_applied"]:
                penalty = item["prepayment_penalty_amount"] + payoff_amount * item["prepayment_penalty_percent"]
                if penalty > 0:
                    item["balance"] += penalty
                    payoff_amount += penalty
                    total_penalties += penalty
                    item["penalty_applied"] = True
            paid = min(item["balance"], remaining_budget)
            item["balance"] -= paid
            remaining_budget -= paid

        for index, item in enumerate(working):
            if item["balance"] <= 0.005 and index not in payoff:
                payoff[index] = {
                    "id": item["id"],
                    "name": item["name"],
                    "month": month,
                    "date": period_end.isoformat(),
                }

        if len(payoff) == len(working):
            break

        interest_next = sum(item["balance"] * item["annual_rate"] / 12.0 + item["fixed_fee"] for item in working if item["balance"] > 0.005)
        if month >= 3 and monthly_budget <= interest_next + 0.005:
            return {"status": "PAYMENT_TOO_LOW", "months": None, "order": [], "payoffs": []}

    if len(payoff) != len(working):
        return {"status": "TOO_LONG", "months": None, "order": [], "payoffs": []}

    payoff_list = sorted(payoff.values(), key=lambda item: (item["month"], item["name"]))
    months = max(item["month"] for item in payoff_list)
    first_win = min(item["month"] for item in payoff_list)
    motivation_score = sum((len(working) - rank) / max(item["month"], 1) for rank, item in enumerate(payoff_list))
    return {
        "status": "OK",
        "months": months,
        "payoff_date": _add_months(start, months).isoformat(),
        "total_interest": round(total_interest, 2),
        "total_fixed_fees": round(total_fees, 2),
        "total_prepayment_penalties": round(total_penalties, 2),
        "total_cost": round(total_interest + total_fees + total_penalties, 2),
        "first_win_month": first_win,
        "motivation_score": motivation_score,
        "order": [{"id": working[index]["id"], "name": working[index]["name"]} for index in order],
        "payoffs": payoff_list,
    }


def calculate_doctor_strange(
    debts: list[dict[str, Any]],
    *,
    extra_payment: float = 0.0,
    start_date: date | None = None,
) -> dict[str, Any]:
    active = [item for item in debts if _number(item.get("remaining_amount")) > 0.005]
    count = len(active)
    if not active:
        return {"status": "EMPTY", "permutations_evaluated": 0, "strategies": {}}

    exhaustive = count <= MAX_EXHAUSTIVE_DEBTS
    if exhaustive:
        orders = itertools.permutations(range(count))
        expected = math.factorial(count)
    else:
        candidates = [
            sorted(range(count), key=lambda i: (-_number(active[i].get("interest_rate")), _number(active[i].get("remaining_amount")))),
            sorted(range(count), key=lambda i: (_number(active[i].get("remaining_amount")), -_number(active[i].get("interest_rate")))),
            sorted(range(count), key=lambda i: (-_number(active[i].get("fixed_fee_amount")), -_number(active[i].get("interest_rate")))),
        ]
        orders = (tuple(item) for item in candidates)
        expected = len(candidates)

    results = [
        result
        for order in orders
        if (result := simulate_order(active, tuple(order), extra_payment=extra_payment, start_date=start_date)).get("status") == "OK"
    ]
    if not results:
        return {"status": "UNPAYABLE", "permutations_evaluated": expected, "strategies": {}}

    costs = [item["total_cost"] for item in results]
    durations = [item["months"] for item in results]
    motivations = [item["motivation_score"] for item in results]
    cost_span = max(max(costs) - min(costs), 1.0)
    duration_span = max(max(durations) - min(durations), 1)
    motivation_span = max(max(motivations) - min(motivations), 1.0)
    for item in results:
        item["balanced_score"] = (
            0.50 * ((item["total_cost"] - min(costs)) / cost_span)
            + 0.30 * ((item["months"] - min(durations)) / duration_span)
            + 0.20 * ((max(motivations) - item["motivation_score"]) / motivation_span)
        )

    cheapest = min(results, key=lambda item: (item["total_cost"], item["months"]))
    fastest = min(results, key=lambda item: (item["months"], item["total_cost"]))
    motivational = max(results, key=lambda item: (item["motivation_score"], -item["total_cost"]))
    balanced = min(results, key=lambda item: (item["balanced_score"], item["total_cost"]))
    return {
        "status": "OK",
        "mode": "exhaustive" if exhaustive else "bounded",
        "debt_count": count,
        "permutations_evaluated": len(results),
        "possible_permutations": math.factorial(count),
        "monthly_budget": round(sum(_number(item.get("monthly_payment")) for item in active) + _number(extra_payment), 2),
        "strategies": {
            "cheapest": cheapest,
            "fastest": fastest,
            "motivational": motivational,
            "balanced": balanced,
        },
        "data_quality": {
            "missing_rates": [item.get("name") for item in active if item.get("interest_rate") is None],
            "missing_minimums": [item.get("name") for item in active if not _number(item.get("monthly_payment"))],
            "prepayment_penalties_assumed_zero": [item.get("name") for item in active if item.get("prepayment_penalty_amount") is None and item.get("prepayment_penalty_percent") is None],
        },
    }
