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


def _monthly_amount_from_frequency(amount: Any, frequency: str | None, interval_months: Any = 1) -> float:
    value = _f(amount)
    freq = (frequency or "monthly").lower().strip()
    interval = max(_f(interval_months) or 1, 1)
    if value <= 0:
        return 0.0
    if freq == "weekly":
        return value * 4.333
    if freq in {"biweekly", "quincenal", "cada_2_semanas"}:
        return value * 2.166
    if freq in {"bimonthly", "every_2_months"}:
        return value / 2
    if freq == "annual":
        return value / 12
    return value / interval


def _is_debt_like_fixed_expense(row: dict[str, Any], debt_names: set[str]) -> bool:
    text = " ".join([
        str(row.get("name") or ""),
        str(row.get("category") or ""),
        str(row.get("payment_method") or ""),
        " ".join(row.get("aliases") or []),
    ]).lower()
    normalized_name = str(row.get("name") or "").lower().strip()
    if normalized_name in debt_names:
        return True
    debt_keywords = [
        "prestamo", "préstamo", "minicuota", "tasa cero", "reloj",
        "tarjeta bac", "banco popular", "deuda", "cuota",
    ]
    return any(keyword in text for keyword in debt_keywords)


def _get_strategy_living_expenses(user_id: int, debts: list[dict[str, Any]]) -> dict[str, Any]:
    """Gastos base para estrategia, sin duplicar deudas.

    fixed_expenses contiene algunos pagos que también existen en debts. Para proyectar
    flujo mensual, la estrategia cuenta las deudas desde debts.monthly_payment y solo
    usa aquí gastos fijos de vida/suscripciones. Si no, se duplican Bac, Minicuota,
    Papá, Reloj y Popular, y el extra mensual sale falso.
    """
    debt_names = {str(d.get("name") or "").lower().strip() for d in debts}
    with get_connection() as conn:
        fixed_rows = [dict(r) for r in conn.execute(
            """
            SELECT id, name, category, expected_amount, frequency, interval_months,
                   payment_method, auto_deducted, aliases, is_active
            FROM fixed_expenses
            WHERE user_id = %s
              AND is_active = TRUE
              AND expected_amount IS NOT NULL
            ORDER BY expected_amount DESC
            """,
            (user_id,),
        ).fetchall()]
        month_start = date.today().replace(day=1).isoformat()
        if date.today().month == 12:
            month_end = date(date.today().year + 1, 1, 1).isoformat()
        else:
            month_end = date(date.today().year, date.today().month + 1, 1).isoformat()
        variable_row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = %s
              AND transaction_type = 'expense'
              AND transaction_date >= %s::date
              AND transaction_date < %s::date
              AND LOWER(COALESCE(category, '')) NOT IN ('tarjeta bac','multiMoney','deuda','familiar','banco popular','reloj')
              AND LOWER(COALESCE(description, '')) NOT LIKE '%%pago%%'
            """,
            (user_id, month_start, month_end),
        ).fetchone()

    included = []
    excluded = []
    total = 0.0
    for row in fixed_rows:
        monthly = _monthly_amount_from_frequency(row.get("expected_amount"), row.get("frequency"), row.get("interval_months"))
        item = {
            "name": row.get("name"),
            "category": row.get("category"),
            "monthly_amount": round(monthly, 2),
            "reason": "debt_duplicate" if _is_debt_like_fixed_expense(row, debt_names) else "living_expense",
        }
        if _is_debt_like_fixed_expense(row, debt_names):
            excluded.append(item)
            continue
        included.append(item)
        total += monthly

    return {
        "fixed_living_total": round(total, 2),
        "variable_current_month_total": round(_f(variable_row["total"] if variable_row else 0), 2),
        "included_fixed": included,
        "excluded_debt_like": excluded,
    }


def _rate_to_monthly(rate: float) -> float:
    if rate <= 0:
        return 0.0
    # En la BD las tasas parecen anuales: 19.5, 26, 35.4.
    return (rate / 100) / 12


def _pick_strategy(debts: list[dict[str, Any]]) -> str:
    # Dictador de deuda: combina motivación y costo.
    # Primero mata saldos pequeños de alto impacto; luego avalancha por tasa.
    return "dictador"


def _sort_debts_for_director(debts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def score(debt: dict[str, Any]) -> tuple:
        balance = _f(debt.get("remaining_amount"))
        rate = _f(debt.get("interest_rate"))
        name = str(debt.get("name") or "").lower()
        # Cerrar deudas pequeñas libera mente y flujo; BAC/Minicuota tienen prioridad por interés.
        small_bucket = 0 if balance <= 200_000 else 1
        high_rate_bucket = 0 if rate >= 25 else 1
        popular_last = 1 if "popular" in name and balance > 1_000_000 else 0
        return (popular_last, small_bucket, high_rate_bucket, -rate, balance)
    return sorted(debts, key=score)


def _simulate_debt_cascade(debts: list[dict[str, Any]], monthly_extra: float) -> tuple[list[dict[str, Any]], int, float]:
    """Simula método cascada: mínimos de todas + sobrante a una deuda.

    Cuando una deuda se cancela, su mínimo se suma automáticamente al ataque mensual
    de la siguiente. Devuelve mes de cierre acumulado por deuda.
    """
    active = []
    for index, debt in enumerate(_sort_debts_for_director(debts)):
        balance = _f(debt.get("remaining_amount"))
        if balance <= 0:
            continue
        minimum = _normalize_payment(debt.get("monthly_payment"), balance)
        active.append({
            "priority": index + 1,
            "name": debt.get("name") or "Deuda",
            "balance": balance,
            "original_balance": balance,
            "minimum": minimum,
            "rate": _rate_to_monthly(_f(debt.get("interest_rate"))),
            "interest_rate": _f(debt.get("interest_rate")),
        })

    minimum_pool = sum(item["minimum"] for item in active)
    payment_pool = minimum_pool + max(monthly_extra, 0)
    if not active:
        return [], 0, payment_pool
    if payment_pool <= 0:
        return [{
            "name": item["name"],
            "remaining_amount": round(item["original_balance"], 2),
            "interest_rate": item["interest_rate"],
            "minimum_payment": round(item["minimum"], 2),
            "recommended_payment": round(item["minimum"], 2),
            "estimated_months": 999,
            "priority": item["priority"],
            "payoff_month": None,
        } for item in active], 999, payment_pool

    payoff: dict[str, dict[str, Any]] = {}
    month = 0
    guard = 0
    while active and guard < 600:
        month += 1
        guard += 1
        # Interés mensual sobre saldos vivos.
        for item in active:
            item["balance"] = item["balance"] * (1 + max(item["rate"], 0))

        remaining_pool = payment_pool
        # Paga mínimos primero para todas las deudas vivas.
        for item in list(active):
            pay = min(item["minimum"], item["balance"], remaining_pool)
            item["balance"] -= pay
            remaining_pool -= pay

        # Todo sobrante ataca la primera deuda de la cola; si muere, sigue con la siguiente.
        while remaining_pool > 0 and active:
            target = active[0]
            pay = min(target["balance"], remaining_pool)
            target["balance"] -= pay
            remaining_pool -= pay
            if target["balance"] <= 1:
                payoff[target["name"]] = {**target, "payoff_month": month}
                active.pop(0)
            else:
                break

        # Limpieza por deudas que murieron con mínimo.
        for item in list(active):
            if item["balance"] <= 1:
                payoff[item["name"]] = {**item, "payoff_month": month}
                active.remove(item)

        # Si ni siquiera cubre interés + mínimos, marcamos sin cierre.
        if month > 3 and payment_pool <= sum(item["balance"] * item["rate"] for item in active):
            break

    result = []
    original_order = _sort_debts_for_director(debts)
    for index, debt in enumerate(original_order):
        name = debt.get("name") or "Deuda"
        balance = _f(debt.get("remaining_amount"))
        minimum = _normalize_payment(debt.get("monthly_payment"), balance)
        closed = payoff.get(name)
        payoff_month = closed.get("payoff_month") if closed else None
        recommended = minimum
        if index == 0:
            recommended = min(balance, minimum + max(monthly_extra, 0))
        result.append({
            "name": name,
            "remaining_amount": round(balance, 2),
            "interest_rate": _f(debt.get("interest_rate")),
            "minimum_payment": round(minimum, 2),
            "recommended_payment": round(recommended, 2),
            "estimated_months": payoff_month if payoff_month is not None else 999,
            "priority": index + 1,
            "payoff_month": payoff_month,
        })

    total_months = max((item.get("payoff_month") or 0) for item in result) if result else 0
    if active and guard >= 600:
        total_months = 999
    return result, total_months, payment_pool


def build_local_strategy_blueprint() -> dict[str, Any]:
    debts = get_debts() or []
    summary = get_financial_summary() or {}
    salary_projection = calculate_monthly_salary_projection() or {}
    user_id = get_current_user_id()

    monthly_income = (
        _f((salary_projection.get("results") or {}).get("projected_net"))
        or _summary_value(summary, "income", "projected_net_income")
        or _summary_value(summary, "income", "total_income")
    )
    debt_minimums = sum(_normalize_payment(d.get("monthly_payment"), d.get("remaining_amount")) for d in debts)
    living = _get_strategy_living_expenses(user_id, debts)
    fixed_living = _f(living.get("fixed_living_total"))
    variable_current = _f(living.get("variable_current_month_total"))

    # V1 conservador: gastos base = fijos de vida. Variable actual queda visible,
    # pero no bloquea toda la estrategia si el histórico está incompleto/sucio.
    monthly_expenses = fixed_living
    safe_extra = max(monthly_income - monthly_expenses - debt_minimums, 0)

    # Regla Director: no asume que TODO el sobrante es deuda; reserva una parte para buffer.
    debt_attack_extra = max(safe_extra * 0.70, 0)
    timeline, total_months, payment_pool = _simulate_debt_cascade(debts, debt_attack_extra)

    total_debt = sum(_f(d.get("remaining_amount")) for d in debts)
    paid_debt = sum(max(_f(d.get("total_amount")) - _f(d.get("remaining_amount")), 0) for d in debts)
    original_debt = total_debt + paid_debt
    progress = round((paid_debt / original_debt) * 100, 2) if original_debt > 0 else 0

    allocation = {
        "ataque_de_deuda": 70 if debts else 0,
        "vida_controlada": 10 if debts else 25,
        "fondo_de_emergencia": 20 if debts else 50,
        "metas_o_inversion": 0 if debts else 25,
    }

    return {
        "month": _month_key(),
        "status": "critical" if (monthly_income <= 0 or total_debt > max(monthly_income * 4, 1)) else "controlled",
        "strategy_type": "dictador_de_deuda",
        "title": "Estrategia Dictador de Deuda" if debts else "Estrategia de Estabilidad",
        "objective": "Eliminar deudas en cascada: mínimos al día y todo excedente controlado a la deuda prioritaria.",
        "monthly_income": round(monthly_income, 2),
        "monthly_expenses": round(monthly_expenses, 2),
        "current_variable_expenses": round(variable_current, 2),
        "monthly_debt_minimums": round(debt_minimums, 2),
        "estimated_extra_cash": round(safe_extra, 2),
        "debt_attack_extra": round(debt_attack_extra, 2),
        "debt_payment_pool": round(payment_pool, 2),
        "fixed_expenses_total": round(fixed_living, 2),
        "living_expense_debug": living,
        "allocation": allocation,
        "total_debt": round(total_debt, 2),
        "debt_progress_percent": progress,
        "estimated_total_months": total_months if timeline else 0,
        "timeline": timeline,
        "rules": [
            "Pagar mínimos de todas las deudas sin fallar.",
            "El excedente mensual ataca primero la deuda #1; al cerrarla, pasa automáticamente a la #2.",
            "Toda OT, bono y sobrante aumenta el ataque de deuda del mes, después de rebajos obligatorios.",
            "VGH reduce el ingreso proyectado y recalcula la estrategia.",
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
