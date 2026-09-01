from __future__ import annotations

import calendar
import math
import re
from datetime import date, datetime, timedelta
from typing import Any

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.emergency_fund import get_salvavidas_state


ESSENTIAL_CATEGORIES = {
    "vivienda",
    "servicios",
    "internet",
    "telefono",
    "teléfono",
    "seguros",
    "comida",
    "salud",
    "transporte",
    "gasolina",
    "automovil",
    "automóvil",
}

SHORT_TERM_DEBT_CATEGORIES = {
    "tarjeta bac",
    "multimoney",
    "banco popular",
    "familiar",
    "otros prestamos",
    "otros préstamos",
    "reloj",
    "automovil",
    "automóvil",
}

MICRO_PURCHASE_LIMIT = 5000.0


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def _today() -> date:
    return date.today()


def _month_bounds(target: date | None = None) -> tuple[date, date]:
    target = target or _today()
    first = target.replace(day=1)
    last_day = calendar.monthrange(target.year, target.month)[1]
    last = target.replace(day=last_day)
    return first, last


def _month_key(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    return str(value)[:7]


def _days_left_in_month(target: date | None = None) -> int:
    target = target or _today()
    _, last = _month_bounds(target)
    return max((last - target).days, 0)


def _rate_to_monthly(rate: float) -> tuple[float, str]:
    """Return monthly decimal rate and transparent interpretation.

    Costa Rican cards often show monthly rates around 2-4%. Long term loans
    are usually registered as annual rates. If the value is <= 5, we treat it
    as monthly percentage; otherwise as annual percentage.
    """
    rate = _as_float(rate)
    if rate <= 0:
        return 0.0, "sin_interes_registrado"
    if rate <= 5:
        return rate / 100.0, "tasa_mensual_porcentaje"
    return (rate / 100.0) / 12.0, "tasa_anual_porcentaje"


def _fetch_transactions() -> list[dict[str, Any]]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id,
                   user_id,
                   transaction_date::date AS transaction_date,
                   description,
                   amount,
                   transaction_type,
                   category,
                   account,
                   source,
                   notes,
                   original_amount,
                   original_currency,
                   exchange_rate,
                   created_at
            FROM transactions
            WHERE workspace_id = %s
            ORDER BY transaction_date::date ASC, id ASC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_debts() -> list[dict[str, Any]]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount,
                   monthly_payment, interest_rate, term_months, payment_day, created_at
            FROM debts
            WHERE workspace_id = %s
            ORDER BY remaining_amount DESC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_goals() -> list[dict[str, Any]]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date, priority, status, created_at
            FROM financial_goals
            WHERE workspace_id = %s
            AND status = 'active'
            ORDER BY created_at ASC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_expenses_table() -> list[dict[str, Any]]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, category, expense_type, description, amount, created_at
            FROM expenses
            WHERE workspace_id = %s
            ORDER BY id ASC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _group_monthly(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    months: dict[str, dict[str, float]] = {}
    for tx in transactions:
        key = _month_key(tx["transaction_date"])
        bucket = months.setdefault(
            key,
            {
                "income": 0.0,
                "loan_received": 0.0,
                "expenses": 0.0,
                "debt_payments": 0.0,
                "investments": 0.0,
                "net_operational": 0.0,
                "net_cash": 0.0,
            },
        )
        amount = _as_float(tx.get("amount"))
        ttype = tx.get("transaction_type")
        if ttype == "income":
            bucket["income"] += amount
        elif ttype in {"loan_received", "loan_disbursement"}:
            bucket["loan_received"] += amount
        elif ttype == "expense":
            bucket["expenses"] += amount
        elif ttype == "debt_payment":
            bucket["debt_payments"] += amount
        elif ttype in {"investment", "investment_deposit"}:
            bucket["investments"] += amount

    result = []
    for month, values in sorted(months.items()):
        values["net_operational"] = values["income"] - values["expenses"] - values["debt_payments"]
        values["net_cash"] = values["income"] + values["loan_received"] - values["expenses"] - values["debt_payments"] - values["investments"]
        result.append({"month": month, **values})
    return result


def get_monthly_financial_flow() -> dict[str, Any]:
    transactions = _fetch_transactions()
    monthly = _group_monthly(transactions)
    if not monthly:
        return {
            "status": "EMPTY",
            "message": "No hay transacciones suficientes para calcular flujo mensual.",
            "months": [],
            "averages": {},
        }

    completed_months = [
        item for item in monthly
        if item["month"] < _today().strftime("%Y-%m")
    ] or monthly

    def avg(key: str) -> float:
        return round(sum(_as_float(item.get(key)) for item in completed_months) / max(len(completed_months), 1), 2)

    return {
        "status": "OK",
        "months": monthly,
        "averages": {
            "income": avg("income"),
            "expenses": avg("expenses"),
            "debt_payments": avg("debt_payments"),
            "net_operational": avg("net_operational"),
            "net_cash": avg("net_cash"),
        },
    }


def get_expense_category_report(limit: int = 12) -> dict[str, Any]:
    transactions = _fetch_transactions()
    totals: dict[str, float] = {}
    monthly: dict[str, dict[str, float]] = {}

    for tx in transactions:
        if tx.get("transaction_type") != "expense":
            continue
        category = (tx.get("category") or "Sin categoría").strip() or "Sin categoría"
        amount = _as_float(tx.get("amount"))
        totals[category] = totals.get(category, 0.0) + amount
        month = _month_key(tx["transaction_date"])
        monthly.setdefault(month, {})
        monthly[month][category] = monthly[month].get(category, 0.0) + amount

    ranked = sorted(
        [{"category": category, "total": round(total, 2)} for category, total in totals.items()],
        key=lambda item: item["total"],
        reverse=True,
    )

    return {
        "status": "OK" if ranked else "EMPTY",
        "top_categories": ranked[:limit],
        "all_categories": ranked,
        "monthly": [
            {"month": month, "categories": [{"category": cat, "total": round(total, 2)} for cat, total in sorted(values.items(), key=lambda x: x[1], reverse=True)]}
            for month, values in sorted(monthly.items())
        ],
    }


def calculate_debt_strategies(extra_payment: float = 0.0) -> dict[str, Any]:
    debts = _fetch_debts()
    normalized = []
    for debt in debts:
        remaining = _as_float(debt.get("remaining_amount"))
        monthly_payment = _as_float(debt.get("monthly_payment"))
        interest_rate = _as_float(debt.get("interest_rate"))
        monthly_rate, rate_type = _rate_to_monthly(interest_rate)
        normalized.append({
            **debt,
            "remaining_amount": remaining,
            "monthly_payment": monthly_payment,
            "interest_rate": interest_rate,
            "monthly_interest_rate": monthly_rate,
            "rate_interpretation": rate_type,
        })

    if not normalized:
        return {
            "status": "EMPTY",
            "message": "No hay deudas registradas para calcular estrategias.",
            "debts": [],
            "snowball": None,
            "avalanche": None,
            "minimum_cost": None,
        }

    snowball_order = sorted(normalized, key=lambda d: (d["remaining_amount"], -d["monthly_interest_rate"]))
    avalanche_order = sorted(normalized, key=lambda d: (-d["monthly_interest_rate"], d["remaining_amount"]))

    def strategy_payload(name: str, order: list[dict[str, Any]]) -> dict[str, Any]:
        first = order[0]
        return {
            "name": name,
            "priority_debt": {
                "id": first.get("id"),
                "name": first.get("name"),
                "remaining_amount": first.get("remaining_amount"),
                "interest_rate": first.get("interest_rate"),
                "monthly_payment": first.get("monthly_payment"),
                "rate_interpretation": first.get("rate_interpretation"),
            },
            "order": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "remaining_amount": item.get("remaining_amount"),
                    "interest_rate": item.get("interest_rate"),
                    "monthly_payment": item.get("monthly_payment"),
                    "reason": (
                        "saldo_mas_bajo" if name == "snowball" else "interes_mas_alto"
                    ),
                }
                for item in order
            ],
        }

    def estimate_minimum_cost(debt: dict[str, Any]) -> dict[str, Any]:
        balance = debt["remaining_amount"]
        payment = max(debt["monthly_payment"], 0)
        rate = debt["monthly_interest_rate"]

        if balance <= 0:
            return {"months": 0, "total_interest": 0.0, "status": "PAID"}
        if payment <= 0:
            return {"months": None, "total_interest": None, "status": "NO_PAYMENT"}
        if rate > 0 and payment <= balance * rate:
            return {"months": None, "total_interest": None, "status": "PAYMENT_TOO_LOW"}

        months = 0
        total_interest = 0.0
        while balance > 0.01 and months < 600:
            interest = balance * rate
            principal = min(payment - interest, balance)
            total_interest += interest
            balance -= principal
            months += 1
        return {
            "months": months,
            "years": round(months / 12, 2),
            "total_interest": round(total_interest, 2),
            "status": "OK" if months < 600 else "TOO_LONG",
        }

    minimum_cost_items = []
    for debt in normalized:
        estimate = estimate_minimum_cost(debt)
        minimum_cost_items.append({
            "id": debt.get("id"),
            "name": debt.get("name"),
            "remaining_amount": debt["remaining_amount"],
            "monthly_payment": debt["monthly_payment"],
            "interest_rate": debt["interest_rate"],
            **estimate,
        })

    return {
        "status": "OK",
        "debts": normalized,
        "snowball": strategy_payload("snowball", snowball_order),
        "avalanche": strategy_payload("avalanche", avalanche_order),
        "minimum_cost": {
            "items": minimum_cost_items,
            "total_remaining": round(sum(item["remaining_amount"] for item in normalized), 2),
            "total_monthly_payment": round(sum(item["monthly_payment"] for item in normalized), 2),
            "total_projected_interest": round(sum(_as_float(item.get("total_interest")) for item in minimum_cost_items), 2),
        },
        "recommended": strategy_payload("avalanche", avalanche_order),
        "note": "Avalancha minimiza intereses. Bola de nieve prioriza motivación pagando saldos pequeños primero.",
    }


def calculate_emergency_fund() -> dict[str, Any]:
    salvavidas = get_salvavidas_state()
    monthly_base = _as_float(salvavidas.get("monthly_base"))
    components = salvavidas.get("components") or {}
    return {
        "status": "OK",
        "current": round(_as_float(salvavidas.get("current_amount")), 2),
        "monthly_base": round(monthly_base, 2),
        "components": {
            "debt_minimums": round(_as_float(components.get("debt_monthly_payments")), 2),
            "protected_expenses": round(_as_float(components.get("protected_expenses")), 2),
        },
        "recommended_1_month": round(monthly_base, 2),
        "recommended_3_months": round(monthly_base * 3, 2),
        "recommended_6_months": round(monthly_base * 6, 2),
        "coverage_months": round(_as_float(salvavidas.get("coverage_months")), 2),
        "progress_percent": round(_as_float(salvavidas.get("progress_percent")), 2),
    }


def calculate_financial_health_score() -> dict[str, Any]:
    flow = get_monthly_financial_flow()
    emergency = calculate_emergency_fund()
    debts = _fetch_debts()

    monthly_saving = max(_as_float(flow.get("averages", {}).get("net_operational")), 0.0)
    emergency_fund_current = _as_float(emergency.get("current"))
    short_term_debt = 0.0

    for debt in debts:
        debt_type = (debt.get("debt_type") or "").lower()
        name = (debt.get("name") or "").lower()
        if debt_type in SHORT_TERM_DEBT_CATEGORIES or any(cat in name for cat in SHORT_TERM_DEBT_CATEGORIES):
            short_term_debt += _as_float(debt.get("remaining_amount"))
        else:
            short_term_debt += _as_float(debt.get("remaining_amount"))

    fixed_expenses = _as_float(emergency.get("monthly_base"))
    denominator = short_term_debt + fixed_expenses
    raw_score = (monthly_saving + emergency_fund_current) / denominator if denominator > 0 else 0.0
    score = max(0, min(round(raw_score * 100, 2), 100))

    if score >= 80:
        level = "strong"
    elif score >= 50:
        level = "stable"
    elif score >= 25:
        level = "fragile"
    else:
        level = "critical"

    return {
        "status": "OK",
        "formula": "(ahorro_mensual + fondo_emergencia) / (deudas_corto_plazo + gastos_fijos)",
        "score": score,
        "raw_value": round(raw_score, 4),
        "level": level,
        "inputs": {
            "monthly_saving_estimate": round(monthly_saving, 2),
            "emergency_fund_current": round(emergency_fund_current, 2),
            "short_term_debt": round(short_term_debt, 2),
            "fixed_expenses_base": round(fixed_expenses, 2),
        },
    }


def detect_micro_spending(limit: int = 12) -> dict[str, Any]:
    transactions = _fetch_transactions()
    groups: dict[str, dict[str, Any]] = {}

    for tx in transactions:
        if tx.get("transaction_type") != "expense":
            continue
        amount = _as_float(tx.get("amount"))
        if amount <= 0 or amount > MICRO_PURCHASE_LIMIT:
            continue

        description = re.sub(r"[^a-zA-ZáéíóúÁÉÍÓÚñÑ0-9 ]", "", tx.get("description") or "").lower().strip()
        key = (tx.get("category") or "Sin categoría").strip() or "Sin categoría"
        if description:
            first_words = " ".join(description.split()[:2])
            key = f"{key} / {first_words}"

        item = groups.setdefault(key, {"label": key, "count": 0, "total": 0.0, "average": 0.0})
        item["count"] += 1
        item["total"] += amount

    items = []
    for item in groups.values():
        item["total"] = round(item["total"], 2)
        item["average"] = round(item["total"] / max(item["count"], 1), 2)
        item["projected_annual"] = round(item["total"] * 12 / max(len({_month_key(tx["transaction_date"]) for tx in transactions}) or 1, 1), 2)
        if item["count"] >= 2:
            items.append(item)

    items.sort(key=lambda x: x["total"], reverse=True)
    return {"status": "OK" if items else "EMPTY", "items": items[:limit]}


def analyze_multicurrency() -> dict[str, Any]:
    transactions = _fetch_transactions()
    items = []
    totals: dict[str, dict[str, float]] = {}
    for tx in transactions:
        currency = (tx.get("original_currency") or "").upper()
        if not currency:
            continue
        original_amount = _as_float(tx.get("original_amount"))
        amount_crc = _as_float(tx.get("amount"))
        exchange_rate = _as_float(tx.get("exchange_rate"))
        totals.setdefault(currency, {"original_total": 0.0, "crc_total": 0.0})
        totals[currency]["original_total"] += original_amount
        totals[currency]["crc_total"] += amount_crc
        items.append({
            "date": str(tx.get("transaction_date")),
            "description": tx.get("description"),
            "category": tx.get("category"),
            "original_amount": original_amount,
            "original_currency": currency,
            "exchange_rate": exchange_rate,
            "amount_crc": amount_crc,
        })

    return {
        "status": "OK" if items else "EMPTY",
        "totals": {
            currency: {
                "original_total": round(values["original_total"], 2),
                "crc_total": round(values["crc_total"], 2),
            }
            for currency, values in totals.items()
        },
        "items": items[-20:],
        "note": "Se conserva el tipo de cambio histórico guardado en cada transacción. No se recalcula contabilidad pasada.",
    }


def reconcile_bank_balance(current_balance: float | None = None, opening_balance: float | None = None) -> dict[str, Any]:
    transactions = _fetch_transactions()
    if current_balance is None or opening_balance is None:
        return {
            "status": "DATA_REQUIRED",
            "message": "Para conciliar necesito balance inicial y saldo actual de la cuenta. No voy a maquillar los números.",
            "required_fields": ["opening_balance", "current_balance"],
        }

    income_types = {"income", "loan_received", "loan_disbursement", "investment_withdrawal"}
    outflow_types = {"expense", "debt_payment", "investment", "investment_deposit", "transfer"}

    inflows = sum(_as_float(tx.get("amount")) for tx in transactions if tx.get("transaction_type") in income_types)
    outflows = sum(_as_float(tx.get("amount")) for tx in transactions if tx.get("transaction_type") in outflow_types)
    expected = _as_float(opening_balance) + inflows - outflows
    diff = round(_as_float(current_balance) - expected, 2)

    return {
        "status": "OK" if abs(diff) < 0.01 else "MISMATCH",
        "opening_balance": _as_float(opening_balance),
        "current_balance": _as_float(current_balance),
        "inflows": round(inflows, 2),
        "outflows": round(outflows, 2),
        "expected_balance": round(expected, 2),
        "difference": diff,
        "message": "Conciliado." if abs(diff) < 0.01 else "Hay desajuste por conciliar. No se modificó ningún dato.",
    }


def forecast_month_end_balance() -> dict[str, Any]:
    today = _today()
    month_start, month_end = _month_bounds(today)
    transactions = _fetch_transactions()
    debts = _fetch_debts()

    current_month = today.strftime("%Y-%m")
    current_transactions = [tx for tx in transactions if _month_key(tx["transaction_date"]) == current_month]
    historical_transactions = [tx for tx in transactions if _month_key(tx["transaction_date"]) < current_month]

    actual_income = sum(_as_float(tx.get("amount")) for tx in current_transactions if tx.get("transaction_type") == "income")
    actual_loans = sum(_as_float(tx.get("amount")) for tx in current_transactions if tx.get("transaction_type") in {"loan_received", "loan_disbursement"})
    actual_expenses = sum(_as_float(tx.get("amount")) for tx in current_transactions if tx.get("transaction_type") == "expense")
    actual_debt_payments = sum(_as_float(tx.get("amount")) for tx in current_transactions if tx.get("transaction_type") == "debt_payment")

    # Historical daily averages from completed months.
    by_month = _group_monthly(historical_transactions)
    avg_expenses = 0.0
    avg_debt_payments = 0.0
    avg_income = 0.0
    if by_month:
        avg_expenses = sum(item["expenses"] for item in by_month) / len(by_month)
        avg_debt_payments = sum(item["debt_payments"] for item in by_month) / len(by_month)
        avg_income = sum(item["income"] for item in by_month) / len(by_month)

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    elapsed_days = max(today.day, 1)
    remaining_ratio = max(days_in_month - elapsed_days, 0) / days_in_month

    expected_remaining_expenses = avg_expenses * remaining_ratio
    expected_remaining_debt = 0.0
    for debt in debts:
        payment_day = debt.get("payment_day")
        if payment_day and int(payment_day) > today.day:
            expected_remaining_debt += _as_float(debt.get("monthly_payment"))

    if expected_remaining_debt <= 0:
        expected_remaining_debt = avg_debt_payments * remaining_ratio

    expected_remaining_income = max(avg_income - actual_income, 0)

    projected_end_balance = actual_income + actual_loans + expected_remaining_income - actual_expenses - actual_debt_payments - expected_remaining_expenses - expected_remaining_debt

    alert = None
    if projected_end_balance < 0:
        alert = {
            "level": "high",
            "message": f"Proyección negativa al cierre del mes: ₡{projected_end_balance:,.0f}.",
        }

    return {
        "status": "OK",
        "month": current_month,
        "current_progress": {
            "actual_income": round(actual_income, 2),
            "actual_loans": round(actual_loans, 2),
            "actual_expenses": round(actual_expenses, 2),
            "actual_debt_payments": round(actual_debt_payments, 2),
        },
        "historical_assumptions": {
            "average_monthly_income": round(avg_income, 2),
            "average_monthly_expenses": round(avg_expenses, 2),
            "average_monthly_debt_payments": round(avg_debt_payments, 2),
            "remaining_ratio": round(remaining_ratio, 4),
        },
        "expected_remaining": {
            "income": round(expected_remaining_income, 2),
            "expenses": round(expected_remaining_expenses, 2),
            "debt_payments": round(expected_remaining_debt, 2),
        },
        "projected_end_balance": round(projected_end_balance, 2),
        "alert": alert,
        "note": "Forecast basado en histórico + pagos esperados. No sustituye conciliación bancaria.",
    }


def simulate_what_if(amount: float, months: int = 1, description: str = "", currency: str = "CRC", exchange_rate: float = 1.0) -> dict[str, Any]:
    months = max(int(months or 1), 1)
    amount_crc = _as_float(amount) * (_as_float(exchange_rate) if currency.upper() != "CRC" else 1.0)
    monthly_payment = amount_crc / months
    flow = get_monthly_financial_flow()
    avg_net = _as_float(flow.get("averages", {}).get("net_operational"))

    today = _today()
    projections = []
    for i in range(months):
        month = today.month + i
        year = today.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        key = f"{year:04d}-{month:02d}"
        projected_net_after = avg_net - monthly_payment
        projections.append({
            "month": key,
            "added_payment": round(monthly_payment, 2),
            "estimated_net_after_purchase": round(projected_net_after, 2),
            "risk": "high" if projected_net_after < 0 else "ok",
        })

    goals = _fetch_goals()
    affected_goals = []
    for goal in goals:
        remaining = max(_as_float(goal.get("target_amount")) - _as_float(goal.get("current_amount")), 0)
        if avg_net <= 0:
            months_delay = None
        else:
            months_delay = math.ceil((monthly_payment * months) / avg_net)
        affected_goals.append({
            "name": goal.get("name"),
            "remaining_amount": round(remaining, 2),
            "estimated_delay_months": months_delay,
        })

    return {
        "status": "OK",
        "scenario": {
            "description": description or "Escenario simulado",
            "amount_crc": round(amount_crc, 2),
            "original_amount": _as_float(amount),
            "currency": currency.upper(),
            "exchange_rate": _as_float(exchange_rate),
            "months": months,
            "monthly_payment": round(monthly_payment, 2),
        },
        "baseline": {
            "average_monthly_net_operational": round(avg_net, 2),
        },
        "projection": projections,
        "affected_goals": affected_goals,
        "recommendation": (
            "No lo haría todavía: el flujo estimado queda negativo."
            if any(item["risk"] == "high" for item in projections)
            else "El escenario parece manejable según el flujo histórico, pero debe validarse contra gastos fijos y deudas reales."
        ),
    }


def smart_cash_allocation() -> dict[str, Any]:
    flow = get_monthly_financial_flow()
    emergency = calculate_emergency_fund()
    debts = calculate_debt_strategies()
    avg_net = _as_float(flow.get("averages", {}).get("net_operational"))
    emergency_target = _as_float(emergency.get("recommended_6_months"))
    savings_total = _as_float(emergency.get("current"))

    if avg_net <= 0:
        return {
            "status": "NO_SURPLUS",
            "message": "No hay excedente promedio. Primero hay que estabilizar flujo.",
            "surplus_estimate": round(avg_net, 2),
        }

    allocations = []
    remaining = avg_net

    if savings_total < emergency_target:
        to_emergency = min(remaining, emergency_target - savings_total)
        allocations.append({
            "target": "Fondo de emergencia",
            "amount": round(to_emergency, 2),
            "reason": "El Salvavidas todavía no cubre los 6 meses objetivo.",
        })
        remaining -= to_emergency

    if remaining > 0 and debts.get("status") == "OK":
        target = debts["avalanche"]["priority_debt"]
        allocations.append({
            "target": f"Deuda prioritaria: {target['name']}",
            "amount": round(remaining, 2),
            "reason": "Después del fondo de emergencia, conviene atacar la deuda de mayor interés.",
        })
        remaining = 0

    if not allocations:
        allocations.append({
            "target": "Inversión",
            "amount": round(avg_net, 2),
            "reason": "Fondo de emergencia cubierto y deuda bajo control.",
        })

    return {
        "status": "OK",
        "surplus_estimate": round(avg_net, 2),
        "emergency_current": round(savings_total, 2),
        "emergency_target_6_months": round(emergency_target, 2),
        "allocations": allocations,
    }


def get_financial_engine_report() -> dict[str, Any]:
    flow = get_monthly_financial_flow()
    categories = get_expense_category_report()
    debts = calculate_debt_strategies()
    emergency = calculate_emergency_fund()
    health = calculate_financial_health_score()
    forecast = forecast_month_end_balance()
    micro = detect_micro_spending()
    multicurrency = analyze_multicurrency()
    allocation = smart_cash_allocation()

    recommendations = []
    if forecast.get("alert"):
        recommendations.append(forecast["alert"]["message"])
    if debts.get("status") == "OK" and debts.get("avalanche"):
        recommendations.append(f"Prioridad avalancha: {debts['avalanche']['priority_debt']['name']}.")
    if emergency.get("monthly_base", 0) > 0:
        recommendations.append(f"Salvavidas objetivo: ₡{emergency['recommended_6_months']:,.0f} para 6 meses de cobertura.")
    if micro.get("items"):
        top = micro["items"][0]
        recommendations.append(f"Gasto hormiga principal: {top['label']} suma ₡{top['total']:,.0f} en el histórico cargado.")

    return {
        "status": "OK",
        "flow": flow,
        "categories": categories,
        "forecast": forecast,
        "health": health,
        "debts": debts,
        "emergency_fund": emergency,
        "smart_cash_allocation": allocation,
        "micro_spending": micro,
        "multicurrency": multicurrency,
        "reconciliation": reconcile_bank_balance(),
        "recommendations": recommendations,
        "data_policy": "El motor calcula solo con datos existentes. Si faltan saldos bancarios o deudas maestras, marca DATA_REQUIRED/EMPTY en vez de inventar.",
    }
