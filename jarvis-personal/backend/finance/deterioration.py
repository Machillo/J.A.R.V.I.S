"""Deterministic financial deterioration signals with human-readable context."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.emergency_fund import get_salvavidas_state
from backend.finance.fixed_expenses import list_fixed_expenses
from backend.finance.intelligence import list_account_balances
from backend.finance.service import get_debts


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _month(value: Any) -> str:
    return str(value or "")[:7]


def get_financial_deterioration() -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    today = date.today()
    current_month = today.strftime("%Y-%m")
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT transaction_date, amount, transaction_type, category, description
               FROM transactions WHERE workspace_id=%s
               AND transaction_date::text ~ '^\\d{4}-\\d{2}-\\d{2}'
               AND transaction_date::date >= (%s::date - INTERVAL '12 months')
               ORDER BY transaction_date ASC""", (workspace_id, today.isoformat())
        ).fetchall()
    monthly: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expenses": 0.0, "debt_payments": 0.0, "net": 0.0})
    for row in rows:
        month = _month(row.get("transaction_date"))
        amount = max(_n(row.get("amount")), 0.0)
        kind = row.get("transaction_type")
        if kind in {"income", "refund", "reimbursement"}:
            monthly[month]["income"] += amount
        elif kind == "debt_payment":
            monthly[month]["debt_payments"] += amount
        elif kind == "expense":
            monthly[month]["expenses"] += amount
    for values in monthly.values():
        values["net"] = values["income"] - values["expenses"] - values["debt_payments"]
        for key in values:
            values[key] = round(values[key], 2)

    ordered = sorted(monthly)
    prior = [monthly[key] for key in ordered if key != current_month][-3:]
    average = {key: round(sum(item[key] for item in prior) / len(prior), 2) if prior else 0.0 for key in ("income", "expenses", "debt_payments", "net")}
    latest_key = current_month if current_month in monthly else (ordered[-1] if ordered else None)
    latest = monthly.get(latest_key, {"income": 0.0, "expenses": 0.0, "debt_payments": 0.0, "net": 0.0})

    accounts = list_account_balances().get("items", [])
    liquidity = round(sum(_n(item.get("balance_crc")) for item in accounts if item.get("include_in_net_worth") and item.get("account_type") != "investment"), 2)
    salvavidas = get_salvavidas_state()
    debts = [item for item in (get_debts() or []) if _n(item.get("remaining_amount")) > 0]
    fixed = list_fixed_expenses(active_only=True)
    recurring = round(sum(max(_n(item.get("expected_amount")), 0) for item in fixed), 2)
    debt_balance = round(sum(_n(item.get("remaining_amount")) for item in debts), 2)
    debt_monthly = round(sum(_n(item.get("monthly_payment")) for item in debts), 2)

    signals: list[dict[str, Any]] = []
    def add_signal(code: str, title: str, severity: str, metric: float, comparison: float, unit: str, context: str):
        signals.append({"code": code, "title": title, "severity": severity, "metric": round(metric, 2), "comparison": round(comparison, 2), "unit": unit, "context": context})

    if prior and latest["net"] < average["net"] - 1:
        add_signal("liquidity", "Liquidez mensual a la baja", "high" if latest["net"] < 0 else "medium", latest["net"], average["net"], "CRC/mes", f"El flujo neto de {latest_key} fue {latest['net']:,.0f}, frente a un promedio reciente de {average['net']:,.0f}.")
    if prior and latest["debt_payments"] > average["debt_payments"] * 1.1 and latest["debt_payments"] > 0:
        add_signal("debt_payments", "Mayor carga de cuotas", "medium", latest["debt_payments"], average["debt_payments"], "CRC/mes", "Los pagos de deuda del último periodo superan el promedio reciente.")
    if prior and latest["expenses"] > average["expenses"] * 1.1 and latest["expenses"] > 0:
        add_signal("expenses", "Gastos creciendo", "medium", latest["expenses"], average["expenses"], "CRC/mes", "Los gastos registrados crecieron más de 10% contra el promedio reciente.")
    coverage = _n(salvavidas.get("coverage_months"))
    if coverage < 1:
        add_signal("salvavidas", "Cobertura Salvavidas baja", "high", coverage, 1, "meses", f"El fondo cubre aproximadamente {coverage:.2f} meses de obligaciones protegidas; la referencia mínima es 1 mes.")
    if liquidity < 0:
        add_signal("available_cash", "Liquidez disponible negativa", "high", liquidity, 0, "CRC", "Las cuentas líquidas conectadas/importadas están por debajo de cero.")

    severity_order = {"high": 0, "medium": 1, "low": 2}
    signals.sort(key=lambda item: severity_order.get(item["severity"], 9))
    cause = signals[0] if signals else None
    return {
        "status": "OK", "generated_at": date.today().isoformat(), "period": {"current": current_month, "compared_months": ordered[-4:]},
        "health": "deteriorating" if any(item["severity"] == "high" for item in signals) else "watch" if signals else "stable",
        "primary_cause": cause,
        "signals": signals,
        "context": {"liquidity_available": liquidity, "salvavidas_coverage_months": round(coverage, 2), "recurring_expected": recurring, "debt_balance": debt_balance, "debt_monthly_payments": debt_monthly, "latest_month": latest, "recent_average": average},
        "monthly": [{"month": key, **monthly[key]} for key in ordered[-6:]],
        "note": "Las señales son informativas y no cambian cuentas, deudas ni transacciones automáticamente.",
    }
