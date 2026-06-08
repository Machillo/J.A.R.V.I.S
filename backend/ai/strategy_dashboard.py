from __future__ import annotations

import json
from datetime import date
from typing import Any

from backend.auth.current_user import get_current_user, get_current_user_id
from backend.core.database import get_connection
from backend.finance.service import get_debts, get_financial_summary
from backend.finance.strategic_engine import get_financial_engine_report
from backend.ai.openai_client import get_active_premium_guides


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _month_key() -> str:
    return date.today().strftime("%Y-%m")


def _months_to_payoff(balance: float, payment: float, monthly_rate: float) -> int | None:
    if balance <= 0:
        return 0
    if payment <= 0:
        return None
    months = 0
    guard = 0
    while balance > 1 and guard < 600:
        balance = balance * (1 + max(monthly_rate, 0)) - payment
        months += 1
        guard += 1
        if payment <= balance * monthly_rate and months > 3:
            return None
    return months if guard < 600 else None


def _rate_to_monthly(rate: float) -> float:
    if rate <= 0:
        return 0.0
    if rate <= 5:
        return rate / 100
    return (rate / 100) / 12


def _pick_strategy(debts: list[dict[str, Any]]) -> str:
    high_interest = [d for d in debts if _f(d.get("interest_rate")) >= 3 or _f(d.get("interest_rate")) >= 25]
    if high_interest:
        return "avalancha"
    return "bola_de_nieve"


def build_local_strategy_blueprint() -> dict[str, Any]:
    debts = get_debts() or []
    summary = get_financial_summary() or {}
    engine = get_financial_engine_report() or {}
    monthly_income = _f(summary.get("monthly_income") or summary.get("income") or summary.get("total_income"))
    monthly_expenses = _f(summary.get("monthly_expenses") or summary.get("expenses") or summary.get("total_expenses"))
    fixed = _f(summary.get("fixed_expenses") or summary.get("monthly_fixed_expenses"))
    debt_minimums = sum(_f(d.get("monthly_payment")) for d in debts)

    flow = engine.get("cashflow") or engine.get("monthly_flow") or {}
    avg_net = _f((flow.get("averages") or {}).get("net_operational") if isinstance(flow, dict) else 0)
    safe_extra = max(avg_net, 0)
    if safe_extra <= 0 and monthly_income > 0:
        safe_extra = max(monthly_income - monthly_expenses - debt_minimums, 0)

    strategy_type = _pick_strategy(debts)
    sorted_debts = sorted(
        debts,
        key=(lambda d: -_f(d.get("interest_rate"))) if strategy_type == "avalancha" else (lambda d: _f(d.get("remaining_amount"))),
    )

    extra_for_debt = max(safe_extra * 0.75, 0)
    allocation = {
        "debt_attack": 70 if debts else 0,
        "emergency_buffer": 20 if debts else 50,
        "controlled_life": 10 if debts else 25,
        "goals_or_investment": 0 if debts else 25,
    }

    timeline = []
    rolling_extra = extra_for_debt
    total_months = 0
    for index, debt in enumerate(sorted_debts):
        balance = _f(debt.get("remaining_amount"))
        minimum = _f(debt.get("monthly_payment"))
        monthly_rate = _rate_to_monthly(_f(debt.get("interest_rate")))
        payment = minimum + (rolling_extra if index == 0 else rolling_extra)
        months = _months_to_payoff(balance, payment, monthly_rate)
        if months is None:
            months = 999
        total_months += months if months < 999 else 0
        rolling_extra += minimum
        timeline.append({
            "name": debt.get("name") or "Deuda",
            "remaining_amount": round(balance, 2),
            "interest_rate": _f(debt.get("interest_rate")),
            "minimum_payment": round(minimum, 2),
            "recommended_payment": round(payment, 2),
            "estimated_months": months,
            "priority": index + 1,
        })

    total_debt = sum(_f(d.get("remaining_amount")) for d in debts)
    paid_debt = sum(max(_f(d.get("total_amount")) - _f(d.get("remaining_amount")), 0) for d in debts)
    original_debt = total_debt + paid_debt
    progress = round((paid_debt / original_debt) * 100, 2) if original_debt > 0 else 0

    return {
        "month": _month_key(),
        "status": "critical" if total_debt > max(monthly_income * 4, 1) else "controlled",
        "strategy_type": strategy_type,
        "title": "Estrategia Dictador de Deuda" if debts else "Estrategia de Estabilidad",
        "objective": "Eliminar deudas de mayor impacto antes de volver a invertir fuerte.",
        "monthly_income": round(monthly_income, 2),
        "monthly_expenses": round(monthly_expenses, 2),
        "monthly_debt_minimums": round(debt_minimums, 2),
        "estimated_extra_cash": round(safe_extra, 2),
        "allocation": allocation,
        "total_debt": round(total_debt, 2),
        "debt_progress_percent": progress,
        "estimated_total_months": total_months if timeline else 0,
        "timeline": timeline,
        "rules": [
            "Toda OT, bono y sobrante va primero a la deuda prioritaria.",
            "Compras no esenciales solo si no reducen el pago objetivo del mes.",
            "Si cambia un gasto fijo o ingreso, se recalcula la estrategia.",
            "No invertir fuerte hasta estabilizar deuda de corto plazo y pagos mínimos.",
        ],
    }


def get_premium_strategy_dashboard() -> dict[str, Any]:
    user = get_current_user()
    guides = get_active_premium_guides(limit=8)
    active = next((g for g in guides if g.get("guide_type") == "financial_strategy"), None)
    blueprint = build_local_strategy_blueprint()
    if active:
        data = active.get("data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        strategy = data.get("strategy_blueprint") or blueprint
        content = active.get("content") or ""
        title = active.get("title") or strategy.get("title") or "Estrategia premium"
    else:
        strategy = blueprint
        content = "Señor, aún no hay una estrategia premium guardada. Ejecuta: 'Jarvis, ejecuta mi estrategia premium'."
        title = strategy.get("title") or "Estrategia base"

    return {
        "status": "OK",
        "user_role": user.get("role"),
        "title": title,
        "content": content,
        "strategy": strategy,
        "updated_at": active.get("created_at") if active else None,
        "has_premium_strategy": bool(active),
    }


def get_additional_card_report() -> dict[str, Any]:
    user_id = get_current_user_id()
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS card_aliases (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                card_last4 TEXT NOT NULL,
                owner_label TEXT NOT NULL,
                relationship TEXT,
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, card_last4)
            )
            """
        )
        aliases = conn.execute(
            """
            SELECT * FROM card_aliases
            WHERE user_id = %s
            ORDER BY is_primary DESC, owner_label ASC
            """,
            (user_id,),
        ).fetchall()
        rows = conn.execute(
            """
            SELECT id, transaction_date, description, amount, transaction_type, category, account, notes, source
            FROM transactions
            WHERE user_id = %s
              AND transaction_type IN ('expense','debt_payment')
            ORDER BY transaction_date DESC, id DESC
            LIMIT 500
            """,
            (user_id,),
        ).fetchall()
        conn.commit()

    alias_list = [dict(a) for a in aliases]
    grouped: dict[str, dict[str, Any]] = {}
    for alias in alias_list:
        owner = alias["owner_label"]
        grouped.setdefault(owner, {"owner": owner, "card_last4": alias["card_last4"], "total": 0.0, "count": 0, "items": []})

    for row in rows:
        haystack = " ".join(str(row.get(k) or "") for k in ["description", "account", "notes", "source"]).lower()
        for alias in alias_list:
            last4 = str(alias.get("card_last4") or "")
            owner = str(alias.get("owner_label") or "")
            if last4 and last4 in haystack or owner.lower() in haystack:
                bucket = grouped.setdefault(owner, {"owner": owner, "card_last4": last4, "total": 0.0, "count": 0, "items": []})
                amount = _f(row.get("amount"))
                bucket["total"] += amount
                bucket["count"] += 1
                if len(bucket["items"]) < 20:
                    bucket["items"].append(dict(row))
                break

    return {"status": "OK", "aliases": alias_list, "cards": list(grouped.values())}
