from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from backend.auth.current_user import get_current_user, get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.service import get_debts, get_financial_summary, calculate_monthly_salary_projection, get_financial_cycle_report
from backend.finance.strategic_engine import get_financial_engine_report, calculate_emergency_fund
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



def _build_allocation_breakdown(allocation: dict[str, Any], base_amount: float) -> dict[str, Any]:
    """Convierte porcentajes de estrategia en montos reales del ciclo actual.

    Fuente de verdad: ingreso neto del ciclo actual. No descuenta aquí gastos o
    deudas porque este bloque representa la distribución directiva del ingreso,
    exactamente como se muestra en Estrategia Premium.
    """
    base = max(_f(base_amount), 0.0)
    items: list[dict[str, Any]] = []
    amounts: dict[str, float] = {}
    running_total = 0.0
    entries = list((allocation or {}).items())

    for index, (key, raw_percent) in enumerate(entries):
        percent = max(_f(raw_percent), 0.0)
        if index == len(entries) - 1:
            # Ajuste de redondeo para que la suma de montos cierre con el ingreso.
            amount = max(base - running_total, 0.0) if sum(_f(v) for _, v in entries) >= 99.99 else round(base * percent / 100, 2)
        else:
            amount = round(base * percent / 100, 2)
            running_total += amount
        amounts[key] = round(amount, 2)
        items.append({
            "key": key,
            "percentage": round(percent, 2),
            "amount": round(amount, 2),
        })

    return {
        "allocation_base_amount": round(base, 2),
        "allocation_amounts": amounts,
        "allocation_items": items,
    }

def _month_key() -> str:
    return date.today().strftime("%Y-%m")


def _months_until(target_date: Any) -> int:
    if not target_date:
        return 12
    try:
        target = datetime.fromisoformat(str(target_date)[:10]).date()
    except Exception:
        return 12
    today = date.today()
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day > today.day:
        months += 1
    return max(months, 1)


def _priority_weight(priority: Any) -> float:
    value = str(priority or "medium").lower().strip()
    if value in {"critical", "critica", "crítica"}:
        return 1.0
    if value in {"high", "alta"}:
        return 0.75
    if value in {"medium", "media"}:
        return 0.45
    return 0.2


def _fetch_active_financial_goals(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date,
                   priority, status, created_at
            FROM financial_goals
            WHERE workspace_id = %s
              AND COALESCE(status, 'active') = 'active'
            ORDER BY
              CASE LOWER(COALESCE(priority, 'medium'))
                WHEN 'critical' THEN 1
                WHEN 'critica' THEN 1
                WHEN 'crítica' THEN 1
                WHEN 'high' THEN 2
                WHEN 'alta' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'media' THEN 3
                ELSE 4
              END,
              target_date ASC NULLS LAST,
              id ASC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _calculate_goal_reserves(goals: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    weighted_total = 0.0
    required_total = 0.0
    critical_total = 0.0
    for goal in goals:
        target = _f(goal.get("target_amount"))
        current = _f(goal.get("current_amount"))
        remaining = max(target - current, 0.0)
        months = _months_until(goal.get("target_date"))
        monthly_required = remaining / months if months else remaining
        weight = _priority_weight(goal.get("priority"))
        auto_reserve = monthly_required * weight
        required_total += monthly_required
        weighted_total += auto_reserve
        if weight >= 1.0:
            critical_total += monthly_required
        items.append({
            "id": goal.get("id"),
            "name": goal.get("name"),
            "priority": goal.get("priority") or "medium",
            "target_amount": round(target, 2),
            "current_amount": round(current, 2),
            "remaining_amount": round(remaining, 2),
            "target_date": goal.get("target_date"),
            "months_left": months,
            "monthly_required": round(monthly_required, 2),
            "auto_reserve": round(auto_reserve, 2),
        })
    return {
        "items": items,
        "monthly_required_all_goals": round(required_total, 2),
        "monthly_auto_reserve": round(weighted_total, 2),
        "critical_monthly_required": round(critical_total, 2),
    }


def _safe_cycle_report() -> dict[str, Any]:
    try:
        return get_financial_cycle_report() or {}
    except Exception:
        return {}


def _safe_emergency_report() -> dict[str, Any]:
    try:
        return calculate_emergency_fund() or {}
    except Exception:
        return {}


def _fetch_savings_total(workspace_id: str) -> float:
    """Dinero reservado explícitamente como ahorro.

    No usamos el balance completo de la cuenta como fondo de emergencia porque
    ese dinero puede estar comprometido con tarjeta, casa, viajes u otras metas.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM savings WHERE workspace_id = %s",
                (workspace_id,),
            ).fetchone()
        return _f(row["total"] if row else 0)
    except Exception:
        return 0.0


def _goal_is_urgent(goal: dict[str, Any]) -> bool:
    remaining = _f(goal.get("remaining_amount"))
    months_left = int(_f(goal.get("months_left")) or 12)
    priority = str(goal.get("priority") or "").lower().strip()
    return (
        remaining > 0
        and months_left <= 2
        and priority in {"critical", "critica", "crítica", "high", "alta"}
    )


def _allocation_from_amounts(amounts: dict[str, float], base: float) -> tuple[dict[str, float], list[dict[str, Any]]]:
    base = max(_f(base), 0.0)
    order = [
        "meta_prioritaria",
        "ataque_de_deuda",
        "fondo_de_emergencia",
        "vida_controlada",
        "inversion",
        "metas_o_inversion",
    ]
    clean = {key: round(max(_f(amounts.get(key)), 0.0), 2) for key in order}
    percentages = {
        key: round((value / base) * 100, 2) if base > 0 else 0.0
        for key, value in clean.items()
    }
    items = [
        {"key": key, "percentage": percentages[key], "amount": clean[key]}
        for key in order
        if clean[key] > 0.01
    ]
    return percentages, items


def _build_dynamic_director_allocation(
    *,
    available_before_allocation: float,
    debts: list[dict[str, Any]],
    goal_reserves: dict[str, Any],
    savings_total: float,
    emergency_monthly_base: float,
) -> dict[str, Any]:
    """Motor de prioridades dinámicas del Director Financiero.

    El porcentaje no es una regla rígida. Primero protege una meta con fecha,
    luego ajusta deuda/seguridad/vida según el tamaño real del colchón.
    """
    base = max(_f(available_before_allocation), 0.0)
    total_debt = sum(max(_f(d.get("remaining_amount")), 0.0) for d in debts)

    monthly_base = max(_f(emergency_monthly_base), 0.0)
    # Con deuda alta no intentamos construir 3-6 meses de golpe. Primero un
    # mini-colchón que evite volver a la tarjeta ante un imprevisto.
    mini_fund_target = min(max(monthly_base * 0.50, 150_000.0), 250_000.0)
    one_month_target = max(monthly_base, mini_fund_target)
    three_month_target = one_month_target * 3
    six_month_target = one_month_target * 6

    goal_items = list(goal_reserves.get("items") or [])
    urgent_goals = [g for g in goal_items if _goal_is_urgent(g)]
    urgent_required = sum(_f(g.get("monthly_required")) for g in urgent_goals)
    if urgent_required <= 0:
        urgent_required = _f(goal_reserves.get("critical_monthly_required"))

    amounts = {
        "meta_prioritaria": 0.0,
        "ataque_de_deuda": 0.0,
        "fondo_de_emergencia": 0.0,
        "vida_controlada": 0.0,
        "inversion": 0.0,
        "metas_o_inversion": 0.0,
    }

    # Capa 1: meta con fecha límite. Se reserva el monto necesario de este ciclo,
    # no un porcentaje inventado.
    goal_now = min(base, max(urgent_required, 0.0))
    amounts["meta_prioritaria"] = goal_now
    remaining = max(base - goal_now, 0.0)

    # Quinta capa: inversión. Arranca pequeña y nunca se financia con deuda ni
    # desplaza una meta urgente. ₡5.000 es la meta base cuando el flujo lo permite.
    investment_target = 5_000.0
    investment_amount = investment_target if remaining >= investment_target else 0.0
    amounts["inversion"] = investment_amount
    remaining = max(remaining - investment_amount, 0.0)

    debt_exists = total_debt > 1
    safety_gap_mini = max(mini_fund_target - savings_total, 0.0)
    safety_gap_month = max(one_month_target - savings_total, 0.0)

    if base <= 0.01:
        mode = "cash_protection"
        mode_label = "PROTECCIÓN DE CAJA"
        mode_reason = "No hay excedente real disponible después de obligaciones."
        remaining_weights = {"debt": 0.0, "emergency": 0.0, "life": 0.0, "goals": 0.0}
    elif urgent_goals or goal_now > 0.01:
        mode = "goal_protection"
        mode_label = "GOAL PROTECTION"
        mode_reason = "Hay una meta prioritaria con fecha cercana; se protege antes de acelerar deuda."
        if debt_exists and safety_gap_mini > 0:
            remaining_weights = {"debt": 0.45, "emergency": 0.40, "life": 0.15, "goals": 0.0}
        elif debt_exists:
            remaining_weights = {"debt": 0.65, "emergency": 0.20, "life": 0.15, "goals": 0.0}
        else:
            remaining_weights = {"debt": 0.0, "emergency": 0.35, "life": 0.15, "goals": 0.50}
    elif debt_exists and safety_gap_mini > 0:
        mode = "debt_safety"
        mode_label = "DEBT + SAFETY"
        mode_reason = "La deuda importa, pero el fondo mínimo todavía es insuficiente para absorber un imprevisto."
        remaining_weights = {"debt": 0.45, "emergency": 0.40, "life": 0.15, "goals": 0.0}
    elif debt_exists and safety_gap_month > 0:
        mode = "debt_attack"
        mode_label = "DEBT ATTACK"
        mode_reason = "El mini-colchón ya existe; se acelera deuda sin dejar de construir un mes de seguridad."
        remaining_weights = {"debt": 0.65, "emergency": 0.20, "life": 0.15, "goals": 0.0}
    elif debt_exists:
        mode = "debt_attack"
        mode_label = "DEBT ATTACK"
        mode_reason = "Hay al menos un mes de seguridad; la mayor parte del excedente puede atacar deuda."
        remaining_weights = {"debt": 0.75, "emergency": 0.10, "life": 0.15, "goals": 0.0}
    else:
        mode = "wealth_building"
        mode_label = "WEALTH BUILDING"
        mode_reason = "Sin deuda prioritaria, el excedente puede construir seguridad, metas e inversión."
        remaining_weights = {"debt": 0.0, "emergency": 0.30, "life": 0.15, "goals": 0.55}

    emergency_raw = remaining * remaining_weights["emergency"]
    # No mandar más al fondo mini de lo necesario cuando el modo está intentando
    # completar ese primer colchón; lo liberado se reasigna a deuda/metas.
    if debt_exists and savings_total < mini_fund_target:
        emergency_amount = min(emergency_raw, safety_gap_mini)
    else:
        emergency_amount = emergency_raw

    freed = max(emergency_raw - emergency_amount, 0.0)
    debt_amount = remaining * remaining_weights["debt"]
    goals_amount = remaining * remaining_weights["goals"]
    life_amount = remaining * remaining_weights["life"]

    if freed > 0:
        if debt_exists:
            debt_amount += freed
        else:
            goals_amount += freed

    amounts["ataque_de_deuda"] = debt_amount
    amounts["fondo_de_emergencia"] = emergency_amount
    amounts["vida_controlada"] = life_amount
    amounts["metas_o_inversion"] = goals_amount

    # Ajuste de redondeo / pesos: cualquier sobrante no asignado se protege.
    assigned = sum(amounts.values())
    remainder = max(base - assigned, 0.0)
    if remainder > 0.01:
        if urgent_goals:
            amounts["meta_prioritaria"] += remainder
        elif debt_exists:
            amounts["ataque_de_deuda"] += remainder
        else:
            amounts["metas_o_inversion"] += remainder

    allocation, items = _allocation_from_amounts(amounts, base)
    safe_to_spend = round(amounts["vida_controlada"], 2)

    if savings_total < mini_fund_target:
        emergency_level = "mini_fund_building"
        emergency_next_target = mini_fund_target
    elif savings_total < one_month_target:
        emergency_level = "one_month_building"
        emergency_next_target = one_month_target
    elif savings_total < three_month_target:
        emergency_level = "three_month_building"
        emergency_next_target = three_month_target
    else:
        emergency_level = "strong"
        emergency_next_target = six_month_target

    return {
        "mode": mode,
        "mode_label": mode_label,
        "mode_reason": mode_reason,
        "allocation": allocation,
        "allocation_amounts": {k: round(v, 2) for k, v in amounts.items()},
        "allocation_items": items,
        "allocation_base_amount": round(base, 2),
        "safe_to_spend": safe_to_spend,
        "emergency": {
            "current": round(savings_total, 2),
            "monthly_base": round(monthly_base, 2),
            "mini_target": round(mini_fund_target, 2),
            "one_month_target": round(one_month_target, 2),
            "three_month_target": round(three_month_target, 2),
            "six_month_target": round(six_month_target, 2),
            "next_target": round(emergency_next_target, 2),
            "gap_to_next_target": round(max(emergency_next_target - savings_total, 0.0), 2),
            "level": emergency_level,
        },
        "urgent_goals": urgent_goals,
        "urgent_goal_reserved": round(goal_now, 2),
        "investment_recommended": round(investment_amount, 2),
        "investment_target": round(investment_target, 2),
    }


def _fetch_investment_portfolio(workspace_id: str) -> dict[str, Any]:
    """Resumen local de inversiones, listo para una futura sincronización IBKR read-only."""
    legacy_value = 0.0
    contributed = 0.0
    realized = unrealized = dividends = taxes = commissions = funding_fees = 0.0
    reserved = 0.0
    try:
        with get_connection() as conn:
            legacy = conn.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM investments WHERE workspace_id = %s",
                (workspace_id,),
            ).fetchone()
            legacy_value = _f(legacy["total"] if legacy else 0)
            # Las tablas nuevas son aditivas y no rompen instalaciones existentes.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS investment_cashflows (
                    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
                    flow_date DATE NOT NULL DEFAULT CURRENT_DATE, flow_type TEXT NOT NULL,
                    amount NUMERIC(14,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
                    source TEXT NOT NULL DEFAULT 'manual', description TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS investment_portfolio_snapshots (
                    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
                    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE, market_value NUMERIC(14,2) NOT NULL DEFAULT 0,
                    contributed_capital NUMERIC(14,2) NOT NULL DEFAULT 0, realized_pnl NUMERIC(14,2) NOT NULL DEFAULT 0,
                    unrealized_pnl NUMERIC(14,2) NOT NULL DEFAULT 0, dividends NUMERIC(14,2) NOT NULL DEFAULT 0,
                    taxes NUMERIC(14,2) NOT NULL DEFAULT 0, commissions NUMERIC(14,2) NOT NULL DEFAULT 0,
                    funding_fees NUMERIC(14,2) NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'USD',
                    source TEXT NOT NULL DEFAULT 'manual', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            snap = conn.execute("""
                SELECT * FROM investment_portfolio_snapshots WHERE workspace_id=%s
                ORDER BY snapshot_date DESC, id DESC LIMIT 1
            """, (workspace_id,)).fetchone()
            reserve = conn.execute("""
                SELECT COALESCE(SUM(CASE WHEN flow_type='reserve' THEN amount WHEN flow_type='reserve_release' THEN -amount ELSE 0 END),0) AS total
                FROM investment_cashflows WHERE workspace_id=%s AND currency='CRC'
            """, (workspace_id,)).fetchone()
            reserved = _f(reserve["total"] if reserve else 0)
            if snap:
                d=dict(snap); legacy_value=_f(d.get('market_value')); contributed=_f(d.get('contributed_capital'))
                realized=_f(d.get('realized_pnl')); unrealized=_f(d.get('unrealized_pnl')); dividends=_f(d.get('dividends'))
                taxes=_f(d.get('taxes')); commissions=_f(d.get('commissions')); funding_fees=_f(d.get('funding_fees'))
            else:
                contributed = legacy_value
    except Exception:
        contributed = legacy_value
    net_pnl = realized + unrealized + dividends - taxes - commissions - funding_fees
    return {
        "market_value": round(legacy_value,2), "contributed_capital": round(contributed,2),
        "realized_pnl": round(realized,2), "unrealized_pnl": round(unrealized,2), "dividends": round(dividends,2),
        "taxes": round(taxes,2), "commissions": round(commissions,2), "funding_fees": round(funding_fees,2),
        "net_pnl": round(net_pnl,2), "reserved_to_invest_crc": round(reserved,2),
        "funding_model": {"wise_percent_estimate": 1.23, "wise_to_ibkr_fixed_usd": 1.13},
        "currency": "USD",
        "sync_status": "manual_ready_for_ibkr",
    }


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


def _get_strategy_living_expenses(workspace_id: str, debts: list[dict[str, Any]]) -> dict[str, Any]:
    """Gastos base usados por Estrategia Premium.

    Decisión V1 de Kenneth:
    - La estrategia NO usa toda la tabla fixed_expenses, porque esa tabla sirve para
      recordatorios/visibilidad y muchas filas duplican deudas o pagos detectables por correos.
    - Para el cálculo duro de salida de deuda solo se descuenta Casa como gasto base fijo.
    - Las deudas se descuentan únicamente desde debts.monthly_payment.
    - Pagos de tarjeta, reloj, minicuotas, Popular, Papá, etc. nunca se duplican aquí.
    """
    debt_names = {str(d.get("name") or "").lower().strip() for d in debts}
    with get_connection() as conn:
        fixed_rows = [dict(r) for r in conn.execute(
            """
            SELECT id, name, category, expected_amount, frequency, interval_months,
                   payment_method, auto_deducted, aliases, is_active
            FROM fixed_expenses
            WHERE workspace_id = %s
              AND is_active = TRUE
              AND expected_amount IS NOT NULL
            ORDER BY expected_amount DESC
            """,
            (workspace_id,),
        ).fetchall()]

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    total = 0.0

    for row in fixed_rows:
        monthly = _monthly_amount_from_frequency(row.get("expected_amount"), row.get("frequency"), row.get("interval_months"))
        name = str(row.get("name") or "").lower().strip()
        is_debt_like = _is_debt_like_fixed_expense(row, debt_names)
        is_strategy_living = name == "casa"
        item = {
            "name": row.get("name"),
            "category": row.get("category"),
            "monthly_amount": round(monthly, 2),
            "reason": "strategy_base_living" if is_strategy_living else ("debt_duplicate" if is_debt_like else "ignored_until_email_or_manual_review"),
        }
        if is_strategy_living:
            included.append(item)
            total += monthly
        else:
            excluded.append(item)

    return {
        "fixed_living_total": round(total, 2),
        "variable_current_month_total": 0.0,
        "included_fixed": included,
        "excluded_from_strategy": excluded,
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


def _simulate_debt_cascade(
    debts: list[dict[str, Any]],
    recurring_monthly_extra: float,
    first_month_extra: float = 0.0,
) -> tuple[list[dict[str, Any]], int, float]:
    """Simula método cascada sin convertir extras únicos en ingreso permanente.

    Reglas:
    - recurring_monthly_extra: sobrante base recurrente de todos los meses.
    - first_month_extra: OT/bono/feriado del mes actual; solo se aplica en el mes 1.
    - Cuando una deuda muere, su mínimo queda dentro del pool y acelera la siguiente.
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
    recurring_pool = minimum_pool + max(recurring_monthly_extra, 0)
    one_time_pool = max(first_month_extra, 0)

    if not active:
        return [], 0, recurring_pool
    if recurring_pool <= 0:
        return [{
            "name": item["name"],
            "remaining_amount": round(item["original_balance"], 2),
            "interest_rate": item["interest_rate"],
            "minimum_payment": round(item["minimum"], 2),
            "recommended_payment": round(item["minimum"], 2),
            "estimated_months": 999,
            "priority": item["priority"],
            "payoff_month": None,
        } for item in active], 999, recurring_pool

    payoff: dict[str, dict[str, Any]] = {}
    month = 0
    guard = 0
    while active and guard < 600:
        month += 1
        guard += 1
        for item in active:
            item["balance"] = item["balance"] * (1 + max(item["rate"], 0))

        remaining_pool = recurring_pool + (one_time_pool if month == 1 else 0)

        # Mínimos primero para todas las deudas vivas.
        for item in list(active):
            pay = min(item["minimum"], item["balance"], remaining_pool)
            item["balance"] -= pay
            remaining_pool -= pay

        # Todo excedente ataca la primera deuda en cola.
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

        for item in list(active):
            if item["balance"] <= 1:
                payoff[item["name"]] = {**item, "payoff_month": month}
                active.remove(item)

        if month > 3 and recurring_pool <= sum(item["balance"] * item["rate"] for item in active):
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
            recommended = min(balance, minimum + max(recurring_monthly_extra, 0) + one_time_pool)
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
    return result, total_months, recurring_pool


def build_local_strategy_blueprint() -> dict[str, Any]:
    """Premium strategy engine.

    Rules Kenneth defined:
    - Do not distribute income bruto. Use actual cycle cashflow.
    - Current month OT/bonus/holiday only affects the current cycle.
    - Debt strategy uses monthly debts, living expenses and active critical goals.
    - Critical goals such as Ecuador must reserve money before extra debt attack.
    """
    debts = get_debts() or []
    summary = get_financial_summary() or {}
    salary_projection = calculate_monthly_salary_projection() or {}
    workspace_id = get_current_workspace_id()
    cycle_report = _safe_cycle_report()

    salary_results = salary_projection.get("results") or {}
    salary_base = salary_projection.get("base") or {}

    recurring_monthly_income = (
        _f(salary_results.get("base_net"))
        or _f(salary_base.get("base_monthly_net"))
        or _summary_value(summary, "income", "projected_net_income")
        or _summary_value(summary, "income", "total_income")
    )
    current_month_income = (
        _f(cycle_report.get("income", {}).get("expected_total"))
        or _f(salary_results.get("projected_net"))
        or recurring_monthly_income
    )
    current_month_extra_net = max(current_month_income - recurring_monthly_income, 0.0)

    configured_debt_payments = sum(_normalize_payment(d.get("monthly_payment"), d.get("remaining_amount")) for d in debts)
    current_debt_payments = _f(cycle_report.get("debts", {}).get("payments_current_period"))
    total_debt = sum(_f(d.get("remaining_amount")) for d in debts)
    paid_debt = sum(max(_f(d.get("total_amount")) - _f(d.get("remaining_amount")), 0) for d in debts)
    original_debt = total_debt + paid_debt
    progress = round((paid_debt / original_debt) * 100, 2) if original_debt > 0 else 0

    goals = _fetch_active_financial_goals(workspace_id)
    goal_reserves = _calculate_goal_reserves(goals)
    critical_goal_required = _f(goal_reserves.get("critical_monthly_required"))
    weighted_goal_required = _f(goal_reserves.get("monthly_auto_reserve"))
    required_goal_reserve = max(critical_goal_required, weighted_goal_required)

    living = _get_strategy_living_expenses(workspace_id, debts)
    recurring_living_expenses = _f(living.get("fixed_living_total"))
    # current_period incluye debt_payment en Finance Overview. Para Strategy
    # usamos spending_only y restamos deuda una sola vez por separado.
    cycle_expenses = _f(cycle_report.get("expenses", {}).get("spending_only"))
    if cycle_expenses <= 0:
        cycle_expenses = max(
            _f(cycle_report.get("expenses", {}).get("current_period"))
            - _f(cycle_report.get("debts", {}).get("payments_current_period")),
            0.0,
        )

    # Current-cycle strategic surplus, exactly as Kenneth defined it:
    # income cycle - variable/current expenses - debt payments already due/paid.
    # Fixed expenses are not subtracted here because they are represented by
    # actual expenses imported/registered in the cycle.
    current_before_goals = current_month_income - cycle_expenses - current_debt_payments
    current_goal_allocation = min(max(current_before_goals, 0.0), required_goal_reserve)
    distribution_base = max(current_before_goals - current_goal_allocation, 0.0)

    # Recurring projection for debt payoff: use the fixed salary baseline and
    # the configured monthly debt payment as the normal debt-payment capacity.
    # OT/bonus from the current month never repeats into future months.
    recurring_before_goals = recurring_monthly_income - recurring_living_expenses - configured_debt_payments
    recurring_goal_allocation = min(max(recurring_before_goals, 0.0), required_goal_reserve)
    recurring_available_after_goals = max(recurring_before_goals - recurring_goal_allocation, 0.0)

    emergency_report = _safe_emergency_report()
    savings_total = _f(emergency_report.get("current"))
    investment_portfolio = _fetch_investment_portfolio(workspace_id)
    emergency_monthly_base = _f(emergency_report.get("monthly_base"))
    if emergency_monthly_base <= 0:
        emergency_monthly_base = recurring_living_expenses + configured_debt_payments

    # Director V2: la base a repartir es el excedente real antes de asignaciones.
    # La meta crítica deja de estar "por fuera" de los porcentajes: ahora aparece
    # explícitamente como la primera capa del plan.
    director = _build_dynamic_director_allocation(
        available_before_allocation=max(current_before_goals, 0.0),
        debts=debts,
        goal_reserves=goal_reserves,
        savings_total=savings_total,
        emergency_monthly_base=emergency_monthly_base,
    )
    allocation = director["allocation"]
    allocation_amounts = director["allocation_amounts"]
    allocation_items = director["allocation_items"]
    allocation_base_amount = _f(director.get("allocation_base_amount"))
    current_goal_allocation = _f(director.get("urgent_goal_reserved"))
    distribution_base = allocation_base_amount
    current_debt_attack_extra = _f(allocation_amounts.get("ataque_de_deuda"))

    # Proyección recurrente: recalcula el mismo criterio usando ingreso base,
    # sin asumir que OT/bonos futuros se repetirán.
    recurring_non_debt_essentials = max(
        emergency_monthly_base - configured_debt_payments,
        recurring_living_expenses,
        0.0,
    )
    recurring_director = _build_dynamic_director_allocation(
        available_before_allocation=max(
            recurring_monthly_income - recurring_non_debt_essentials - configured_debt_payments,
            0.0,
        ),
        debts=debts,
        goal_reserves=goal_reserves,
        savings_total=savings_total,
        emergency_monthly_base=emergency_monthly_base,
    )
    recurring_debt_attack_extra = _f(recurring_director.get("allocation_amounts", {}).get("ataque_de_deuda"))

    base_timeline, base_total_months, base_payment_pool = _simulate_debt_cascade(
        debts,
        recurring_monthly_extra=recurring_debt_attack_extra,
        first_month_extra=0,
    )
    timeline, total_months, payment_pool = _simulate_debt_cascade(
        debts,
        recurring_monthly_extra=recurring_debt_attack_extra,
        first_month_extra=current_debt_attack_extra,
    )

    months_saved = 0
    if base_total_months and total_months and base_total_months < 999 and total_months < 999:
        months_saved = max(base_total_months - total_months, 0)

    deficit_after_mandatory = current_month_income - cycle_expenses - current_debt_payments
    no_free_cash = deficit_after_mandatory <= 0
    mode = director.get("mode") or "cash_protection"
    mode_label = director.get("mode_label") or "PROTECCIÓN DE CAJA"
    status = "critical" if no_free_cash else ("controlled" if total_debt > 0 else "strong")
    objective = (
        "Señor, este ciclo no tiene flujo libre. Primero cubra obligaciones; no hay dinero seguro para gastar o abonar extra."
        if no_free_cash else
        f"Señor, modo {mode_label}: {director.get('mode_reason')}"
    )

    rules = [
        "Primero se cubren gastos reales y pagos mínimos; nunca se usa el saldo total de una deuda como gasto mensual.",
        "Una meta urgente con fecha se reserva antes de repartir el resto del excedente.",
        "El fondo de emergencia se construye por etapas: mini-colchón, 1 mes, 3 meses y luego 6 meses esenciales.",
        "La deuda recibe más peso conforme mejora el colchón; los porcentajes cambian con la situación y no son una regla fija.",
        "Vida controlada es dinero que sí puede gastarse sin tocar obligaciones, meta prioritaria, seguridad ni inversión.",
        "Inversión empieza con una meta base de ₡5.000 solo cuando existe flujo; se acumula antes de fondear IBKR para reducir costos.",
        "OT, bonos, feriados y vacaciones aceleran únicamente el ciclo donde realmente ocurren.",
    ]
    if no_free_cash:
        rules.insert(0, "Señor, no hay dinero libre para repartir este ciclo; no se fabrica ataque de deuda.")

    return {
        "month": _month_key(),
        "status": status,
        "strategy_type": "director_financiero_dinamico_v2",
        "title": "Estrategia de Protección de Flujo" if no_free_cash else f"Director Financiero · {mode_label}",
        "mode": mode,
        "mode_label": mode_label,
        "mode_reason": director.get("mode_reason"),
        "objective": objective,
        "monthly_income": round(current_month_income, 2),
        "recurring_monthly_income": round(recurring_monthly_income, 2),
        "current_month_extra_net": round(current_month_extra_net, 2),
        "current_month_one_time_debt_boost": round(current_debt_attack_extra, 2),
        "monthly_expenses": round(cycle_expenses, 2),
        "recurring_living_expenses": round(recurring_living_expenses, 2),
        "recurring_essential_living_base": round(recurring_non_debt_essentials, 2),
        "current_variable_expenses": round(cycle_expenses, 2),
        "monthly_debt_minimums": round(configured_debt_payments, 2),
        "configured_debt_payments": round(configured_debt_payments, 2),
        "current_debt_payments": round(current_debt_payments, 2),
        "debt_payments_reserved": round(current_debt_payments, 2),
        "critical_goals_reserved": round(current_goal_allocation, 2),
        "current_goal_allocation": round(current_goal_allocation, 2),
        "available_before_goals": round(current_before_goals, 2),
        "strategic_available_cash": round(distribution_base, 2),
        "estimated_extra_cash": round(distribution_base, 2),
        "base_estimated_extra_cash": round(_f(recurring_director.get("allocation_base_amount")), 2),
        "safe_to_spend": round(_f(director.get("safe_to_spend")), 2),
        "investment_recommended": round(_f(director.get("investment_recommended")), 2),
        "investment_target": round(_f(director.get("investment_target")), 2),
        "investment_portfolio": investment_portfolio,
        "emergency_fund": director.get("emergency") or {},
        "urgent_goals": director.get("urgent_goals") or [],
        "debt_attack_extra": round(current_debt_attack_extra, 2),
        "recurring_debt_attack_extra": round(recurring_debt_attack_extra, 2),
        "debt_payment_pool": round(payment_pool, 2),
        "base_debt_payment_pool": round(base_payment_pool, 2),
        "fixed_expenses_total": round(cycle_expenses, 2),
        "living_expense_debug": living,
        "salary_projection_debug": salary_projection,
        "cycle_report_debug": cycle_report,
        "goals": goals,
        "goal_reserves": goal_reserves,
        "allocation": allocation,
        "allocation_base_amount": round(allocation_base_amount, 2),
        "allocation_amounts": allocation_amounts,
        "allocation_items": allocation_items,
        "total_debt": round(total_debt, 2),
        "debt_progress_percent": progress,
        "estimated_total_months": total_months if timeline else 0,
        "base_estimated_total_months": base_total_months if base_timeline else 0,
        "months_saved_by_current_extras": months_saved,
        "timeline": timeline,
        "base_timeline": base_timeline,
        "rules": rules,
    }

def get_premium_strategy_dashboard() -> dict[str, Any]:
    """Return a live strategy calculated from the current database state.

    Saved premium guides are intentionally not used as the source of truth: they
    are historical artifacts and made the dashboard appear frozen after finance
    data changed.
    """
    user = get_current_user()
    strategy = build_local_strategy_blueprint()
    return {
        "status": "OK",
        "user_role": user.get("role"),
        "title": strategy.get("title") or "Estrategia activa",
        "content": strategy.get("objective") or "",
        "strategy": strategy,
        "updated_at": datetime.now().isoformat(),
        "has_premium_strategy": True,
        "source": "live_database",
    }


def get_additional_card_report() -> dict[str, Any]:
    """Report only additional-card spending, not Kenneth's primary card.

    Email-confirmed movements are joined back to email_transaction_candidates so
    the report can use card_last4/card_owner parsed from BAC notifications. This
    avoids guessing from generic transaction notes and prevents Kenneth's primary
    card 3131 from appearing in the additional-cards page.
    """
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
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
                UNIQUE(workspace_id, card_last4)
            )
            """
        )
        aliases = conn.execute(
            """
            SELECT *
            FROM card_aliases
            WHERE workspace_id = %s
              AND COALESCE(is_primary, FALSE) = FALSE
              AND LOWER(owner_label) NOT IN ('kenneth', 'kenneth andres')
            ORDER BY owner_label ASC, card_last4 ASC
            """,
            (workspace_id,),
        ).fetchall()
        rows = conn.execute(
            """
            SELECT
                t.id,
                t.transaction_date,
                t.description,
                t.amount,
                t.transaction_type,
                t.category,
                t.account,
                t.notes,
                t.source,
                c.card_last4,
                c.card_owner,
                c.email_message_id,
                c.id AS candidate_id
            FROM transactions t
            LEFT JOIN email_transaction_candidates c
              ON c.transaction_id = t.id AND c.workspace_id = t.workspace_id
            WHERE t.workspace_id = %s
              AND t.transaction_type = 'expense'
              AND COALESCE(c.status, '') IN ('confirmed','auto_saved')
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT 5000
            """,
            (workspace_id,),
        ).fetchall()
        conn.commit()

    alias_list = [dict(a) for a in aliases]
    additional_last4 = {str(a.get("card_last4") or ""): dict(a) for a in alias_list if a.get("card_last4")}
    additional_owners = {str(a.get("owner_label") or "").strip().lower() for a in alias_list}

    grouped: dict[str, dict[str, Any]] = {}
    for alias in alias_list:
        owner = alias["owner_label"]
        grouped.setdefault(owner, {
            "owner": owner,
            "card_last4": alias["card_last4"],
            "cards": [],
            "total": 0.0,
            "count": 0,
            "items": [],
        })
        grouped[owner]["cards"].append(alias["card_last4"])

    for row in rows:
        item = dict(row)
        last4 = str(item.get("card_last4") or "")
        owner = str(item.get("card_owner") or "").strip()

        alias = additional_last4.get(last4)
        if alias:
            owner = alias["owner_label"]
        elif owner.lower() not in additional_owners:
            # Primary card, no card metadata, or unknown owner: not an
            # additional-card movement.
            continue

        bucket = grouped.setdefault(owner, {
            "owner": owner,
            "card_last4": last4,
            "cards": [last4] if last4 else [],
            "total": 0.0,
            "count": 0,
            "items": [],
        })
        bucket["items"].append(item)

    for bucket in grouped.values():
        unique_cards = []
        for last4 in bucket.get("cards") or []:
            if last4 and last4 not in unique_cards:
                unique_cards.append(last4)
        bucket["cards"] = unique_cards
        bucket["items"] = sorted(
            bucket.get("items") or [],
            key=lambda item: (str(item.get("transaction_date") or ""), int(item.get("id") or 0)),
            reverse=True,
        )
        bucket["count"] = len(bucket["items"])
        bucket["total"] = round(sum(_f(item.get("amount")) for item in bucket["items"]), 2)

    return {"status": "OK", "aliases": alias_list, "cards": list(grouped.values())}
