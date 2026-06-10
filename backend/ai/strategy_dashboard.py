from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from backend.auth.current_user import get_current_user, get_current_user_id
from backend.core.database import get_connection
from backend.finance.service import get_debts, get_financial_summary, calculate_monthly_salary_projection, get_financial_cycle_report
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


def _fetch_active_financial_goals(user_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date,
                   priority, status, created_at
            FROM financial_goals
            WHERE user_id = %s
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
            (user_id,),
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
            WHERE user_id = %s
              AND is_active = TRUE
              AND expected_amount IS NOT NULL
            ORDER BY expected_amount DESC
            """,
            (user_id,),
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
    debts = get_debts() or []
    summary = get_financial_summary() or {}
    salary_projection = calculate_monthly_salary_projection() or {}
    user_id = get_current_user_id()
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

    current_month_extra_net = max(current_month_income - recurring_monthly_income, 0)
    current_month_negative_adjustments = min(current_month_income - recurring_monthly_income, 0)

    debt_minimums = sum(_normalize_payment(d.get("monthly_payment"), d.get("remaining_amount")) for d in debts)
    total_debt = sum(_f(d.get("remaining_amount")) for d in debts)
    paid_debt = sum(max(_f(d.get("total_amount")) - _f(d.get("remaining_amount")), 0) for d in debts)
    original_debt = total_debt + paid_debt
    progress = round((paid_debt / original_debt) * 100, 2) if original_debt > 0 else 0

    goals = _fetch_active_financial_goals(user_id)
    goal_reserves = _calculate_goal_reserves(goals)
    critical_goal_required = _f(goal_reserves.get("critical_monthly_required"))
    weighted_goal_required = _f(goal_reserves.get("monthly_auto_reserve"))
    goal_required = max(critical_goal_required, weighted_goal_required)

    cycle_expenses = _f(cycle_report.get("expenses", {}).get("current_period"))
    cycle_debt_payments = _f(cycle_report.get("debts", {}).get("payments_current_period"))
    if cycle_debt_payments <= 0:
        # Si aún no hay pagos reales registrados en el ciclo, al menos reserve los mínimos.
        cycle_debt_payments = debt_minimums

    available_before_goals = current_month_income - cycle_expenses - cycle_debt_payments
    goals_allocation_amount = max(min(goal_required, max(available_before_goals, 0.0)), 0.0)
    strategic_available = max(available_before_goals - goals_allocation_amount, 0.0)

    if strategic_available <= 0.01:
        allocation = {
            "ataque_de_deuda": 0,
            "vida_controlada": 0,
            "fondo_de_emergencia": 0,
            "metas_o_inversion": 100 if goals_allocation_amount > 0 else 0,
        }
        allocation_amounts = {
            "ataque_de_deuda": 0.0,
            "vida_controlada": 0.0,
            "fondo_de_emergencia": 0.0,
            "metas_o_inversion": round(goals_allocation_amount, 2),
        }
    else:
        debt_percent = 70 if debts else 0
        living_percent = 10 if debts else 25
        emergency_percent = 20 if debts else 50
        goal_percent = 0 if goals_allocation_amount <= 0 else round((goals_allocation_amount / max(available_before_goals, 1)) * 100, 2)
        allocation = {
            "ataque_de_deuda": debt_percent,
            "vida_controlada": living_percent,
            "fondo_de_emergencia": emergency_percent,
            "metas_o_inversion": goal_percent,
        }
        allocation_amounts = {
            "ataque_de_deuda": round(strategic_available * debt_percent / 100, 2),
            "vida_controlada": round(strategic_available * living_percent / 100, 2),
            "fondo_de_emergencia": round(strategic_available * emergency_percent / 100, 2),
            "metas_o_inversion": round(goals_allocation_amount, 2),
        }

    allocation_items = [
        {"key": key, "percentage": allocation.get(key, 0), "amount": allocation_amounts.get(key, 0)}
        for key in ["ataque_de_deuda", "vida_controlada", "fondo_de_emergencia", "metas_o_inversion"]
    ]

    debt_attack_extra = _f(allocation_amounts.get("ataque_de_deuda"))
    base_timeline, base_total_months, base_payment_pool = _simulate_debt_cascade(
        debts,
        recurring_monthly_extra=0,
        first_month_extra=0,
    )
    one_time_debt_boost = max(debt_attack_extra + current_month_negative_adjustments, 0)
    timeline, total_months, payment_pool = _simulate_debt_cascade(
        debts,
        recurring_monthly_extra=0,
        first_month_extra=one_time_debt_boost,
    )

    months_saved = 0
    if base_total_months and total_months and base_total_months < 999 and total_months < 999:
        months_saved = max(base_total_months - total_months, 0)

    deficit_after_goals = available_before_goals - goal_required
    no_free_cash = deficit_after_goals <= 0
    status = "critical" if no_free_cash or (recurring_monthly_income <= 0 or total_debt > max(recurring_monthly_income * 4, 1)) else "controlled"
    objective = (
        "Cubrir el déficit del ciclo y proteger metas críticas antes de atacar deuda."
        if no_free_cash else
        "Proteger metas críticas y dirigir solo el excedente real a la deuda prioritaria."
    )

    rules = [
        "No distribuir dinero inexistente: la estrategia usa ingreso menos gastos reales, deudas y metas críticas.",
        "Las metas críticas tienen prioridad sobre ataque extra de deuda, emergencia e inversión.",
        "Pagar mínimos de todas las deudas sin fallar.",
        "Solo el excedente real del ciclo puede ir a ataque de deuda.",
        "OT, bono y feriados solo aceleran el mes actual; no se proyectan como ingreso permanente.",
    ]
    if no_free_cash:
        rules.insert(0, "Señor, el ciclo no tiene flujo libre: primero se cubre el faltante.")

    return {
        "month": _month_key(),
        "status": status,
        "strategy_type": "flujo_real_con_metas_criticas",
        "title": "Estrategia de Flujo Real" if no_free_cash else "Estrategia Dictador de Deuda",
        "objective": objective,
        "monthly_income": round(current_month_income, 2),
        "recurring_monthly_income": round(recurring_monthly_income, 2),
        "current_month_extra_net": round(current_month_extra_net, 2),
        "current_month_one_time_debt_boost": round(one_time_debt_boost, 2),
        "monthly_expenses": round(cycle_expenses, 2),
        "current_variable_expenses": round(cycle_expenses, 2),
        "monthly_debt_minimums": round(debt_minimums, 2),
        "debt_payments_reserved": round(cycle_debt_payments, 2),
        "critical_goals_reserved": round(goal_required, 2),
        "available_before_goals": round(available_before_goals, 2),
        "strategic_available_cash": round(strategic_available, 2),
        "estimated_extra_cash": round(strategic_available, 2),
        "base_estimated_extra_cash": round(max(available_before_goals, 0), 2),
        "debt_attack_extra": round(debt_attack_extra, 2),
        "debt_payment_pool": round(payment_pool, 2),
        "base_debt_payment_pool": round(base_payment_pool, 2),
        "fixed_expenses_total": round(cycle_expenses, 2),
        "salary_projection_debug": salary_projection,
        "cycle_report_debug": cycle_report,
        "goals": goals,
        "goal_reserves": goal_reserves,
        "allocation": allocation,
        "allocation_base_amount": round(max(available_before_goals, 0), 2),
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
        saved_strategy = data.get("strategy_blueprint") or {}
        if isinstance(saved_strategy, dict):
            # La guía guardada puede contener porcentajes viejos.  La matemática
            # del tablero siempre debe venir del blueprint recalculado contra BD.
            strategy = {**saved_strategy, **blueprint}
        else:
            strategy = blueprint
        content = active.get("content") or ""
        title = strategy.get("title") or active.get("title") or "Estrategia premium"
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
    """Report only additional-card spending, not Kenneth's primary card.

    Email-confirmed movements are joined back to email_transaction_candidates so
    the report can use card_last4/card_owner parsed from BAC notifications. This
    avoids guessing from generic transaction notes and prevents Kenneth's primary
    card 3131 from appearing in the additional-cards page.
    """
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
            SELECT *
            FROM card_aliases
            WHERE user_id = %s
              AND COALESCE(is_primary, FALSE) = FALSE
              AND LOWER(owner_label) NOT IN ('kenneth', 'kenneth andres')
            ORDER BY owner_label ASC, card_last4 ASC
            """,
            (user_id,),
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
              ON c.transaction_id = t.id AND c.user_id = t.user_id
            WHERE t.user_id = %s
              AND t.transaction_type = 'expense'
              AND COALESCE(c.status, '') IN ('confirmed','auto_saved')
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT 5000
            """,
            (user_id,),
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
