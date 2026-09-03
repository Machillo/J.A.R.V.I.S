from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from backend.auth.current_user import get_current_user, get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.service import get_debts, get_financial_summary, calculate_monthly_salary_projection, get_financial_cycle_report
from backend.finance.emergency_fund import get_salvavidas_state
from backend.finance.fixed_expenses import get_fixed_expense_status
from backend.ai.openai_client import get_active_premium_guides
from backend.integrations.ibkr_readonly import ensure_ibkr_tables


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
    """Convierte porcentajes de estrategia en montos reales del sobrante del ciclo.

    La base que recibe esta función ya excluyó gastos y obligaciones. Strategy
    nunca distribuye el ingreso bruto: únicamente reparte el sobrante real.
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
    # El Salvavidas oficial siempre usa exactamente 1/3/6 meses del costo mensual
    # protegido. El mini-colchón solo es una etapa intermedia y nunca puede ser
    # mayor que la meta oficial de un mes.
    mini_fund_target = (
        min(monthly_base, min(max(monthly_base * 0.50, 150_000.0), 250_000.0))
        if monthly_base > 0
        else 0.0
    )
    one_month_target = monthly_base
    three_month_target = monthly_base * 3
    six_month_target = monthly_base * 6

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
            ensure_ibkr_tables(conn)
            snap = conn.execute("""
                SELECT * FROM investment_portfolio_snapshots
                WHERE workspace_id=%s AND included_in_net_worth=TRUE
                ORDER BY snapshot_at DESC NULLS LAST, snapshot_date DESC, id DESC LIMIT 1
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
    raw_aliases = row.get("aliases") or []
    if isinstance(raw_aliases, str):
        try:
            parsed = json.loads(raw_aliases)
            raw_aliases = parsed if isinstance(parsed, list) else [raw_aliases]
        except Exception:
            raw_aliases = [part.strip() for part in raw_aliases.split(",") if part.strip()]
    aliases = [str(item) for item in raw_aliases if str(item).strip()]
    text = " ".join([
        str(row.get("name") or ""),
        str(row.get("category") or ""),
        str(row.get("payment_method") or ""),
        " ".join(aliases),
    ]).lower()
    normalized_name = str(row.get("name") or "").lower().strip()
    if normalized_name in debt_names:
        return True
    debt_keywords = [
        "prestamo", "préstamo", "minicuota", "tasa cero", "reloj",
        "tarjeta bac", "banco popular", "deuda",
    ]
    return any(keyword in text for keyword in debt_keywords)

def _get_strategy_living_expenses(workspace_id: str, debts: list[dict[str, Any]]) -> dict[str, Any]:
    """Recurring living commitments used for forward projections.

    Debts stay authoritative in ``debts`` and are never duplicated from
    ``fixed_expenses``. For the non-debt recurring base we keep the commitments
    Kenneth marked as unavoidable in V1: house and phone line.
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
        category = str(row.get("category") or "").lower().strip()
        is_debt_like = _is_debt_like_fixed_expense(row, debt_names)
        is_house = name == "casa" or category == "vivienda"
        is_phone_line = "línea" in name or "linea" in name or category in {"teléfono", "telefono", "telefonía", "telefonia"}
        is_strategy_living = (is_house or is_phone_line) and not is_debt_like
        item = {
            "id": row.get("id"),
            "name": row.get("name"),
            "category": row.get("category"),
            "monthly_amount": round(monthly, 2),
            "reason": "mandatory_living" if is_strategy_living else ("debt_duplicate" if is_debt_like else "not_mandatory_for_projection"),
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


def _parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _transaction_date_expr_sql() -> str:
    raw = "NULLIF(BTRIM(transaction_date::text), '')"
    return (
        "CASE "
        f"WHEN {raw} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' "
        f"THEN SUBSTRING({raw} FROM 1 FOR 10)::date "
        "ELSE NULL END"
    )


def _fetch_post_cut_expenses(workspace_id: str, cycle_report: dict[str, Any]) -> dict[str, Any]:
    """Expenses registered after the card statement cut, inside the active finance cycle.

    Finance Overview intentionally freezes the payable card statement at the cut.
    Strategy is more conservative: once a new expense appears after that cut, it
    immediately reduces the money that can be distributed, even if it will be paid
    on the next card statement.
    """
    cut_end = _parse_iso_date((cycle_report.get("expense_cycle") or {}).get("end"))
    cycle_end = _parse_iso_date((cycle_report.get("cycle") or {}).get("end"))
    if not cut_end or not cycle_end:
        return {"total": 0.0, "count": 0, "start": None, "end": None}

    start = cut_end + timedelta(days=1)
    end = min(date.today(), cycle_end)
    if start > end:
        return {"total": 0.0, "count": 0, "start": start.isoformat(), "end": end.isoformat()}

    expr = _transaction_date_expr_sql()
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
            FROM transactions
            WHERE workspace_id = %s
              AND LOWER(BTRIM(COALESCE(transaction_type, ''))) = 'expense'
              AND {expr} >= %s::date
              AND {expr} < %s::date
            """,
            (workspace_id, start.isoformat(), (end + timedelta(days=1)).isoformat()),
        ).fetchone()

    return {
        "total": round(_f(row.get("total") if row else 0), 2),
        "count": int(_f(row.get("count") if row else 0)),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def _month_keys_between(start: date, end: date) -> list[str]:
    keys: list[str] = []
    cursor = start.replace(day=1)
    limit = end.replace(day=1)
    while cursor <= limit and len(keys) < 24:
        keys.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return keys


def _pending_mandatory_fixed_expenses(
    cycle_report: dict[str, Any],
    salvavidas: dict[str, Any],
) -> dict[str, Any]:
    """Reserve mandatory recurrent bills that are due in this cycle and not detected as paid."""
    cycle_start = _parse_iso_date((cycle_report.get("cycle") or {}).get("start"))
    cycle_end = _parse_iso_date((cycle_report.get("cycle") or {}).get("end"))
    mandatory = list(salvavidas.get("mandatory_expenses") or [])
    mandatory_ids = {int(item["id"]) for item in mandatory if item.get("id") is not None}
    if not cycle_start or not cycle_end or not mandatory_ids:
        return {"total": 0.0, "items": []}

    pending: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for month_key in _month_keys_between(cycle_start, cycle_end):
        try:
            status_report = get_fixed_expense_status(month_key) or {}
        except Exception:
            continue
        for item in status_report.get("items") or []:
            fixed = item.get("fixed_expense") or {}
            try:
                fixed_id = int(fixed.get("id"))
            except Exception:
                continue
            if fixed_id not in mandatory_ids or not item.get("due_this_month"):
                continue
            due = _parse_iso_date(item.get("due_date"))
            if not due or due < cycle_start or due > cycle_end:
                continue
            key = (fixed_id, due.isoformat())
            if key in seen:
                continue
            seen.add(key)
            if str(item.get("status") or "").lower() == "paid":
                continue
            amount = max(_f(item.get("expected_amount")), 0.0)
            pending.append({
                "id": fixed_id,
                "name": fixed.get("name") or "Pago recurrente",
                "due_date": due.isoformat(),
                "amount": round(amount, 2),
                "status": item.get("status") or "pending",
            })

    return {
        "total": round(sum(_f(item.get("amount")) for item in pending), 2),
        "items": pending,
    }


def _add_months_iso(start: date, months: int | None) -> str | None:
    if not months or months <= 0 or months >= 999:
        return None
    month_index = (start.month - 1) + int(months)
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(start.day, last_day)).isoformat()


def _build_current_priority(
    *,
    no_free_cash: bool,
    director: dict[str, Any],
    timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    amounts = director.get("allocation_amounts") or {}
    urgent_goals = director.get("urgent_goals") or []
    emergency = director.get("emergency") or {}

    if no_free_cash:
        return {
            "kind": "cash",
            "title": "Cubrir obligaciones del ciclo",
            "detail": "No hay sobrante real para repartir todavía.",
        }
    if urgent_goals and _f(amounts.get("meta_prioritaria")) > 0:
        goal = urgent_goals[0]
        return {
            "kind": "goal",
            "title": f"Meta: {goal.get('name') or 'prioritaria'}",
            "detail": "JARVIS la protege primero porque tiene una fecha/prioridad activa.",
        }
    if timeline and _f(amounts.get("ataque_de_deuda")) > 0:
        target = timeline[0]
        return {
            "kind": "debt",
            "title": f"Atacar deuda: {target.get('name') or 'deuda prioritaria'}",
            "detail": "El sobrante destinado a deuda se concentra primero en esta obligación.",
        }
    if _f(amounts.get("fondo_de_emergencia")) > 0 and _f(emergency.get("current")) < _f(emergency.get("six_month_target")):
        return {
            "kind": "salvavidas",
            "title": "Construir Salvavidas",
            "detail": "La prioridad es aumentar tus meses de cobertura antes de asumir más riesgo.",
        }
    if _f(amounts.get("inversion")) > 0:
        return {
            "kind": "investment",
            "title": "Construir patrimonio",
            "detail": "Las obligaciones están cubiertas y existe margen para invertir.",
        }
    return {
        "kind": "control",
        "title": "Mantener control del flujo",
        "detail": director.get("mode_reason") or "JARVIS mantiene el sobrante bajo control.",
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
        debt_type = str(debt.get("debt_type") or "other").lower().strip()

        # Primero costo financiero real. Una Tasa Cero al 0% debe mantenerse al
        # día, pero nunca desplazar una deuda que sí está cobrando intereses.
        no_interest_bucket = 1 if rate <= 0.0001 else 0
        zero_rate_financing_last = 1 if debt_type == "tasa_cero" and rate <= 0.0001 else 0
        high_rate_bucket = 0 if rate >= 25 else 1
        small_bucket = 0 if balance <= 200_000 else 1
        popular_last = 1 if "popular" in name and balance > 1_000_000 else 0
        return (zero_rate_financing_last, no_interest_bucket, popular_last, high_rate_bucket, small_bucket, -rate, balance)

    return sorted(debts, key=score)


def _simulate_debt_cascade(
    debts: list[dict[str, Any]],
    recurring_monthly_extra: float,
    first_month_extra: float = 0.0,
) -> tuple[list[dict[str, Any]], int, float]:
    """Simulate an active-debt cascade without keeping cancelled/paid rows in the route."""
    ordered_active = [
        debt for debt in _sort_debts_for_director(debts)
        if _f(debt.get("remaining_amount")) > 0.01
    ]
    active: list[dict[str, Any]] = []
    for debt in ordered_active:
        balance = _f(debt.get("remaining_amount"))
        minimum = _normalize_payment(debt.get("monthly_payment"), balance)
        active.append({
            "priority": len(active) + 1,
            "id": debt.get("id"),
            "name": debt.get("name") or "Deuda",
            "debt_type": debt.get("debt_type") or "other",
            "balance": balance,
            "original_balance": balance,
            "minimum": minimum,
            "rate": _rate_to_monthly(_f(debt.get("interest_rate"))),
            "interest_rate": _f(debt.get("interest_rate")),
        })

    minimum_pool = sum(item["minimum"] for item in active)
    recurring_pool = minimum_pool + max(recurring_monthly_extra, 0)
    first_month_adjustment = _f(first_month_extra)

    if not active:
        return [], 0, recurring_pool
    if recurring_pool <= 0:
        return [{
            "id": item.get("id"),
            "name": item["name"],
            "debt_type": item.get("debt_type") or "other",
            "remaining_amount": round(item["original_balance"], 2),
            "interest_rate": item["interest_rate"],
            "minimum_payment": round(item["minimum"], 2),
            "recommended_payment": round(item["minimum"], 2),
            "estimated_months": 999,
            "priority": item["priority"],
            "payoff_month": None,
            "estimated_payoff_date": None,
        } for item in active], 999, recurring_pool

    payoff: dict[int, dict[str, Any]] = {}
    month = 0
    guard = 0
    working = [dict(item) for item in active]
    while working and guard < 600:
        month += 1
        guard += 1
        for item in working:
            item["balance"] = item["balance"] * (1 + max(item["rate"], 0))

        remaining_pool = max(recurring_pool + (first_month_adjustment if month == 1 else 0), 0.0)

        # Pay every active minimum first.
        for item in list(working):
            pay = min(item["minimum"], item["balance"], remaining_pool)
            item["balance"] -= pay
            remaining_pool -= pay

        # The remaining pool attacks the highest-priority active debt.
        while remaining_pool > 0.01 and working:
            target = working[0]
            pay = min(target["balance"], remaining_pool)
            target["balance"] -= pay
            remaining_pool -= pay
            if target["balance"] <= 1:
                payoff[int(target["id"] or target["priority"])] = {**target, "payoff_month": month}
                working.pop(0)
            else:
                break

        for item in list(working):
            if item["balance"] <= 1:
                payoff[int(item["id"] or item["priority"])] = {**item, "payoff_month": month}
                working.remove(item)

        if month > 3 and working and recurring_pool <= sum(item["balance"] * item["rate"] for item in working):
            break

    result: list[dict[str, Any]] = []
    for index, debt in enumerate(ordered_active):
        balance = _f(debt.get("remaining_amount"))
        minimum = _normalize_payment(debt.get("monthly_payment"), balance)
        debt_key = int(debt.get("id") or index + 1)
        closed = payoff.get(debt_key)
        payoff_month = closed.get("payoff_month") if closed else None
        recommended = minimum
        if index == 0:
            first_month_attack = max(max(recurring_monthly_extra, 0) + first_month_adjustment, 0.0)
            recommended = min(balance, minimum + first_month_attack)
        result.append({
            "id": debt.get("id"),
            "name": debt.get("name") or "Deuda",
            "debt_type": debt.get("debt_type") or "other",
            "remaining_amount": round(balance, 2),
            "interest_rate": _f(debt.get("interest_rate")),
            "minimum_payment": round(minimum, 2),
            "recommended_payment": round(recommended, 2),
            "estimated_months": payoff_month if payoff_month is not None else 999,
            "priority": index + 1,
            "payoff_month": payoff_month,
            "estimated_payoff_date": _add_months_iso(date.today(), payoff_month),
        })

    total_months = max((item.get("payoff_month") or 0) for item in result) if result else 0
    if working:
        total_months = 999
    return result, total_months, recurring_pool

def build_local_strategy_blueprint() -> dict[str, Any]:
    """Live personal strategy focused on real surplus, not gross income.

    Current-cycle distribution follows one rule: obligations and every expense
    already registered come out first. Only the remainder is distributed among
    Salvavidas, debt attack, goals, investment and free life money.
    """
    all_debts = get_debts() or []
    debts = [debt for debt in all_debts if _f(debt.get("remaining_amount")) > 0.01]
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

    configured_debt_payments = sum(
        _normalize_payment(debt.get("monthly_payment"), debt.get("remaining_amount"))
        for debt in debts
    )
    current_debt_payments = _f(cycle_report.get("debts", {}).get("payments_current_period"))
    debt_commitment_current_cycle = max(configured_debt_payments, current_debt_payments)

    total_debt = sum(max(_f(debt.get("remaining_amount")), 0.0) for debt in debts)
    original_debt = sum(
        max(_f(debt.get("total_amount")), _f(debt.get("remaining_amount")), 0.0)
        for debt in all_debts
    )
    paid_debt = max(original_debt - total_debt, 0.0)
    progress = round((paid_debt / original_debt) * 100, 2) if original_debt > 0 else 0.0

    goals = _fetch_active_financial_goals(workspace_id)
    goal_reserves = _calculate_goal_reserves(goals)

    living = _get_strategy_living_expenses(workspace_id, debts)
    recurring_living_expenses = _f(living.get("fixed_living_total"))

    try:
        salvavidas = get_salvavidas_state() or {}
    except Exception:
        salvavidas = {}

    statement_spending = _f(cycle_report.get("expenses", {}).get("spending_only"))
    if statement_spending <= 0:
        statement_spending = max(
            _f(cycle_report.get("expenses", {}).get("current_period"))
            - _f(cycle_report.get("debts", {}).get("payments_current_period")),
            0.0,
        )
    post_cut = _fetch_post_cut_expenses(workspace_id, cycle_report)
    new_spending_after_cut = _f(post_cut.get("total"))
    committed_spending = statement_spending + new_spending_after_cut

    pending_mandatory = _pending_mandatory_fixed_expenses(cycle_report, salvavidas)
    mandatory_fixed_pending = _f(pending_mandatory.get("total"))

    # The current distribution base is the true remainder after all known outflows:
    # payable statement spending + any new expense after cut + at least one full
    # monthly debt obligation + mandatory recurrent bills still pending.
    current_before_allocation = (
        current_month_income
        - committed_spending
        - debt_commitment_current_cycle
        - mandatory_fixed_pending
    )

    # Strategy and the Salvavidas screen must share the same source of truth.
    # The current balance is manual in V1; the monthly base is recalculated live
    # from active debts + Casa/Línea + user-protected recurring expenses.
    savings_total = max(_f(salvavidas.get("current_amount")), 0.0)
    emergency_monthly_base = max(_f(salvavidas.get("monthly_base")), 0.0)
    if emergency_monthly_base <= 0:
        emergency_monthly_base = recurring_living_expenses + configured_debt_payments

    investment_portfolio = _fetch_investment_portfolio(workspace_id)

    director = _build_dynamic_director_allocation(
        available_before_allocation=max(current_before_allocation, 0.0),
        debts=debts,
        goal_reserves=goal_reserves,
        savings_total=savings_total,
        emergency_monthly_base=emergency_monthly_base,
    )
    allocation = director.get("allocation") or {}
    allocation_amounts = director.get("allocation_amounts") or {}
    allocation_items = director.get("allocation_items") or []
    allocation_base_amount = _f(director.get("allocation_base_amount"))
    current_goal_allocation = _f(director.get("urgent_goal_reserved"))
    current_debt_attack_extra = _f(allocation_amounts.get("ataque_de_deuda"))

    # Future payoff estimate uses recurring income only. Protected Salvavidas
    # expenses are respected as recurring life costs, and current OT/bonus is not
    # projected forever.
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
    recurring_debt_attack_extra = _f(
        (recurring_director.get("allocation_amounts") or {}).get("ataque_de_deuda")
    )

    base_timeline, base_total_months, base_payment_pool = _simulate_debt_cascade(
        debts,
        recurring_monthly_extra=recurring_debt_attack_extra,
        first_month_extra=0.0,
    )
    first_month_adjustment = current_debt_attack_extra - recurring_debt_attack_extra
    timeline, total_months, payment_pool = _simulate_debt_cascade(
        debts,
        recurring_monthly_extra=recurring_debt_attack_extra,
        first_month_extra=first_month_adjustment,
    )

    months_saved = 0
    if base_total_months and total_months and base_total_months < 999 and total_months < 999:
        months_saved = max(base_total_months - total_months, 0)

    no_free_cash = current_before_allocation <= 0.0
    mode = director.get("mode") or "cash_protection"
    mode_label = director.get("mode_label") or "PROTECCIÓN DE CAJA"
    status = "critical" if no_free_cash else ("controlled" if total_debt > 0 else "strong")
    objective = (
        "Señor, este ciclo no tiene sobrante real. Primero cubra obligaciones y gastos registrados."
        if no_free_cash
        else f"Señor, modo {mode_label}: {director.get('mode_reason')}"
    )

    priority = _build_current_priority(
        no_free_cash=no_free_cash,
        director=director,
        timeline=timeline,
    )

    debt_free_date = _add_months_iso(date.today(), total_months if total_months < 999 else None)
    base_debt_free_date = _add_months_iso(date.today(), base_total_months if base_total_months < 999 else None)
    first_month_one_time_boost = max(first_month_adjustment, 0.0)

    rules = [
        "Solo se distribuye el sobrante que queda después de obligaciones y gastos ya registrados.",
        "Un gasto nuevo reduce el sobrante del ciclo desde que aparece, aunque no sea una deuda.",
        "Las deudas activas reservan al menos su cuota mensual completa antes de repartir dinero.",
        "Casa y línea se tratan como pagos recurrentes obligatorios; las demás protecciones del Salvavidas son configurables.",
        "OT, bonos, feriados y vacaciones aceleran únicamente el ciclo donde realmente ocurren.",
    ]

    return {
        "month": _month_key(),
        "status": status,
        "strategy_type": "director_financiero_dinamico_v3",
        "title": "Estrategia de Protección de Flujo" if no_free_cash else f"Director Financiero · {mode_label}",
        "mode": mode,
        "mode_label": mode_label,
        "mode_reason": director.get("mode_reason"),
        "objective": objective,
        "priority": priority,
        "monthly_income": round(current_month_income, 2),
        "recurring_monthly_income": round(recurring_monthly_income, 2),
        "current_month_extra_net": round(current_month_extra_net, 2),
        "current_month_one_time_debt_boost": round(first_month_one_time_boost, 2),
        "monthly_expenses": round(committed_spending, 2),
        "statement_expenses": round(statement_spending, 2),
        "new_expenses_after_cut": round(new_spending_after_cut, 2),
        "new_expenses_after_cut_count": int(_f(post_cut.get("count"))),
        "new_expenses_after_cut_window": {
            "start": post_cut.get("start"),
            "end": post_cut.get("end"),
        },
        "mandatory_fixed_pending": round(mandatory_fixed_pending, 2),
        "mandatory_fixed_pending_items": pending_mandatory.get("items") or [],
        "recurring_living_expenses": round(recurring_living_expenses, 2),
        "recurring_essential_living_base": round(recurring_non_debt_essentials, 2),
        "current_variable_expenses": round(committed_spending, 2),
        "monthly_debt_minimums": round(configured_debt_payments, 2),
        "configured_debt_payments": round(configured_debt_payments, 2),
        "current_debt_payments": round(current_debt_payments, 2),
        "debt_commitment_current_cycle": round(debt_commitment_current_cycle, 2),
        "debt_payments_reserved": round(debt_commitment_current_cycle, 2),
        "critical_goals_reserved": round(current_goal_allocation, 2),
        "current_goal_allocation": round(current_goal_allocation, 2),
        "available_before_goals": round(current_before_allocation, 2),
        "strategic_available_cash": round(allocation_base_amount, 2),
        "estimated_extra_cash": round(allocation_base_amount, 2),
        "base_estimated_extra_cash": round(_f(recurring_director.get("allocation_base_amount")), 2),
        "safe_to_spend": round(_f(director.get("safe_to_spend")), 2),
        "investment_recommended": round(_f(director.get("investment_recommended")), 2),
        "investment_target": round(_f(director.get("investment_target")), 2),
        "investment_portfolio": investment_portfolio,
        "emergency_fund": director.get("emergency") or {},
        "salvavidas": salvavidas,
        "urgent_goals": director.get("urgent_goals") or [],
        "debt_attack_extra": round(current_debt_attack_extra, 2),
        "recurring_debt_attack_extra": round(recurring_debt_attack_extra, 2),
        "debt_payment_pool": round(payment_pool, 2),
        "base_debt_payment_pool": round(base_payment_pool, 2),
        "fixed_expenses_total": round(committed_spending, 2),
        "living_expense_debug": living,
        "salary_projection_debug": salary_projection,
        "cycle_report_debug": cycle_report,
        "goals": goals,
        "goal_reserves": goal_reserves,
        "allocation": allocation,
        "allocation_base_amount": round(allocation_base_amount, 2),
        "allocation_amounts": allocation_amounts,
        "allocation_items": allocation_items,
        "allocation_total": round(sum(_f(item.get("amount")) for item in allocation_items), 2),
        "distribution_formula": {
            "income": round(current_month_income, 2),
            "statement_spending": round(statement_spending, 2),
            "new_spending_after_cut": round(new_spending_after_cut, 2),
            "debt_commitment": round(debt_commitment_current_cycle, 2),
            "mandatory_fixed_pending": round(mandatory_fixed_pending, 2),
            "surplus": round(allocation_base_amount, 2),
        },
        "total_debt": round(total_debt, 2),
        "debt_original_total": round(original_debt, 2),
        "debt_paid_total": round(paid_debt, 2),
        "debt_progress_percent": progress,
        "estimated_total_months": total_months if timeline else 0,
        "estimated_debt_free_date": debt_free_date,
        "base_estimated_total_months": base_total_months if base_timeline else 0,
        "base_estimated_debt_free_date": base_debt_free_date,
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
