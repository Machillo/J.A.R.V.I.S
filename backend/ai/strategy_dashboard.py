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

    salary_results = salary_projection.get("results") or {}
    salary_base = salary_projection.get("base") or {}
    salary_adjustments = salary_projection.get("adjustments") or {}

    recurring_monthly_income = (
        _f(salary_results.get("base_net"))
        or _f(salary_base.get("base_monthly_net"))
        or _summary_value(summary, "income", "projected_net_income")
        or _summary_value(summary, "income", "total_income")
    )
    current_month_income = (
        _f(salary_results.get("projected_net"))
        or recurring_monthly_income
    )

    # OT, bonos y feriados son eventos del mes actual: NO se multiplican a meses futuros.
    current_month_extra_net = max(current_month_income - recurring_monthly_income, 0)
    current_month_negative_adjustments = min(current_month_income - recurring_monthly_income, 0)

    debt_minimums = sum(_normalize_payment(d.get("monthly_payment"), d.get("remaining_amount")) for d in debts)
    living = _get_strategy_living_expenses(user_id, debts)
    fixed_living = _f(living.get("fixed_living_total"))
    variable_current = _f(living.get("variable_current_month_total"))

    monthly_expenses = fixed_living

    # Escenario base: solo salario recurrente, Casa y mínimos de deuda.
    base_safe_extra = max(recurring_monthly_income - monthly_expenses - debt_minimums, 0)
    base_debt_attack_extra = max(base_safe_extra * 0.70, 0)
    base_timeline, base_total_months, base_payment_pool = _simulate_debt_cascade(
        debts,
        recurring_monthly_extra=base_debt_attack_extra,
        first_month_extra=0,
    )

    # Escenario mes actual: mismo futuro base, pero OT/bonos/feriados solo aceleran el mes 1.
    # Si hubo VGH, reduce el ataque del mes 1.
    one_time_debt_boost = max(current_month_extra_net * 0.70 + current_month_negative_adjustments, 0)
    timeline, total_months, payment_pool = _simulate_debt_cascade(
        debts,
        recurring_monthly_extra=base_debt_attack_extra,
        first_month_extra=one_time_debt_boost,
    )

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
    allocation_breakdown = _build_allocation_breakdown(allocation, current_month_income)

    months_saved = 0
    if base_total_months and total_months and base_total_months < 999 and total_months < 999:
        months_saved = max(base_total_months - total_months, 0)

    return {
        "month": _month_key(),
        "status": "critical" if (recurring_monthly_income <= 0 or total_debt > max(recurring_monthly_income * 4, 1)) else "controlled",
        "strategy_type": "dictador_de_deuda",
        "title": "Estrategia Dictador de Deuda" if debts else "Estrategia de Estabilidad",
        "objective": "Eliminar deudas en cascada: mínimos al día y excedente recurrente a la deuda prioritaria.",
        "monthly_income": round(current_month_income, 2),
        "recurring_monthly_income": round(recurring_monthly_income, 2),
        "current_month_extra_net": round(current_month_extra_net, 2),
        "current_month_one_time_debt_boost": round(one_time_debt_boost, 2),
        "monthly_expenses": round(monthly_expenses, 2),
        "current_variable_expenses": round(variable_current, 2),
        "monthly_debt_minimums": round(debt_minimums, 2),
        "estimated_extra_cash": round(max(current_month_income - monthly_expenses - debt_minimums, 0), 2),
        "base_estimated_extra_cash": round(base_safe_extra, 2),
        "debt_attack_extra": round(base_debt_attack_extra, 2),
        "debt_payment_pool": round(payment_pool, 2),
        "base_debt_payment_pool": round(base_payment_pool, 2),
        "fixed_expenses_total": round(fixed_living, 2),
        "living_expense_debug": living,
        "salary_projection_debug": salary_projection,
        "allocation": allocation,
        **allocation_breakdown,
        "total_debt": round(total_debt, 2),
        "debt_progress_percent": progress,
        "estimated_total_months": total_months if timeline else 0,
        "base_estimated_total_months": base_total_months if base_timeline else 0,
        "months_saved_by_current_extras": months_saved,
        "timeline": timeline,
        "base_timeline": base_timeline,
        "rules": [
            "Pagar mínimos de todas las deudas sin fallar.",
            "El excedente recurrente ataca primero la deuda #1; al cerrarla, pasa automáticamente a la #2.",
            "OT, bono y feriados solo aceleran el mes actual; no se proyectan como ingreso permanente.",
            "VGH reduce el ingreso del mes actual y puede bajar el ataque de deuda del mes.",
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
        if isinstance(strategy, dict):
            # Compatibilidad con guías guardadas antes de que existieran montos.
            strategy = {**blueprint, **strategy}
            if not strategy.get("allocation_amounts") or not strategy.get("allocation_items"):
                strategy.update(_build_allocation_breakdown(strategy.get("allocation") or {}, _f(strategy.get("monthly_income"))))
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
