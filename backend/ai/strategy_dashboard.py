from __future__ import annotations

import json
from datetime import date
from typing import Any

from backend.auth.current_user import get_current_user, get_current_user_id
from backend.core.database import get_connection
from backend.finance.service import get_debts, get_financial_summary, calculate_monthly_salary_projection
from backend.finance.strategic_engine import get_financial_engine_report
from backend.ai.openai_client import get_active_premium_guides


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _summary_value(summary: dict[str, Any], *path: str) -> float:
    current: Any = summary
    for key in path:
        if not isinstance(current, dict):
            return 0.0
        current = current.get(key)
    return _f(current)


def _normalize_payment(value: Any, remaining_amount: Any = 0) -> float:
    value = _f(value)
    remaining = _f(remaining_amount)
    if value <= 0:
        return 0.0
    if remaining > 0 and value > remaining and value >= 100000:
        scaled = value / 100
        if scaled <= max(remaining, 1_000_000):
            return round(scaled, 2)
    if value >= 1_000_000:
        return round(value / 100, 2)
    return round(value, 2)


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
    salary_projection = calculate_monthly_salary_projection() or {}
    # Salario mensual neto proyectado: base fija + OT/bonos/VGH del mes.
    # No depende de movimientos bancarios importados.
    monthly_income = (
        _f((salary_projection.get("results") or {}).get("projected_net"))
        or _summary_value(summary, "income", "projected_net_income")
        or _summary_value(summary, "income", "total_income")
    )
    monthly_expenses = (
        _summary_value(summary, "expenses", "expenses_total")
        or (
            _summary_value(summary, "expenses", "fixed_expenses_total")
            + _summary_value(summary, "expenses", "variable_expenses_total")
            + _summary_value(summary, "expenses", "one_time_expenses_total")
        )
    )
    fixed = _summary_value(summary, "expenses", "fixed_expenses_total")
    debt_minimums = sum(_normalize_payment(d.get("monthly_payment"), d.get("remaining_amount")) for d in debts)

    # En V1 la estrategia NO debe inventar excedentes desde históricos importados.
    # El extra real sale del salario fijo + eventos del mes (OT/bonos/VGH) menos gastos y mínimos.
    # Esto evita pagos recomendados absurdos cuando el histórico tiene préstamos o importaciones sucias.
    safe_extra = max(monthly_income - monthly_expenses - debt_minimums, 0)

    strategy_type = _pick_strategy(debts)
    sorted_debts = sorted(
        debts,
        key=(lambda d: -_f(d.get("interest_rate"))) if strategy_type == "avalancha" else (lambda d: _f(d.get("remaining_amount"))),
    )

    extra_for_debt = max(safe_extra * 0.75, 0)
    # Límite defensivo: nunca recomendar pagos imposibles.
    # Si no hay ingreso, no se inventa extra; si hay ingreso, se respeta el 70% máximo de ataque de deuda.
    max_target_payment = max(monthly_income * 0.70, 0)
    allocation = {
        "ataque_de_deuda": 70 if debts else 0,
        "vida_controlada": 10 if debts else 25,
        "fondo_de_emergencia": 20 if debts else 50,
        "metas_o_inversion": 0 if debts else 25,
    }

    timeline = []
    rolling_extra = extra_for_debt
    total_months = 0
    for index, debt in enumerate(sorted_debts):
        balance = _f(debt.get("remaining_amount"))
        minimum = _normalize_payment(debt.get("monthly_payment"), debt.get("remaining_amount"))
        monthly_rate = _rate_to_monthly(_f(debt.get("interest_rate")))
        # Durante la ruta, solo la deuda prioritaria recibe el extra.
        # Las demás mantienen mínimo hasta que les toque el turno.
        if index == 0:
            payment = minimum + rolling_extra
        else:
            payment = minimum
        if max_target_payment > 0:
            payment = min(payment, max(minimum, max_target_payment))
        payment = min(payment, balance) if balance > 0 else payment
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
        "status": "critical" if (monthly_income <= 0 or total_debt > max(monthly_income * 4, 1)) else "controlled",
        "strategy_type": strategy_type,
        "title": "Estrategia Dictador de Deuda" if debts else "Estrategia de Estabilidad",
        "objective": "Eliminar deudas de mayor impacto antes de volver a invertir fuerte.",
        "monthly_income": round(monthly_income, 2),
        "monthly_expenses": round(monthly_expenses, 2),
        "monthly_debt_minimums": round(debt_minimums, 2),
        "estimated_extra_cash": round(safe_extra, 2),
        "fixed_expenses_total": round(fixed, 2),
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
        content = "Señor, aún no hay una estrategia premium guardada. Ejecute la estrategia premium para activar el modo Director."
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
