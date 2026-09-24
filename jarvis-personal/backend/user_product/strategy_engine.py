from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any
from backend.core.i18n import plural, tx


def _money(value: Any) -> float:
    return round(max(float(value or 0), 0.0), 2)


def _months_to_payoff(balance: float, monthly_payment: float, annual_rate: float | None) -> int | None:
    balance, payment = _money(balance), _money(monthly_payment)
    if balance <= 0:
        return 0
    if payment <= 0:
        return None
    if annual_rate is None or annual_rate <= 0:
        return ceil(balance / payment)
    monthly_rate = float(annual_rate) / 100 / 12
    remaining = balance
    for month in range(1, 1201):
        interest = remaining * monthly_rate
        if payment <= interest:
            return None
        remaining = remaining + interest - payment
        if remaining <= 0.01:
            return month
    return None


def _record_order(value: Any) -> float:
    """Oldest record first on exact ties (same result as the snapshot's ORDER BY id)."""
    try:
        return -float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _debt_score(debt: dict) -> tuple:
    """Deterministic hybrid: known APR first, then due date and smaller balance."""
    rate = debt.get("interest_rate")
    known_rate = rate is not None
    return (
        1 if known_rate else 0,
        float(rate or 0),
        -(int(debt.get("payment_day") or 32)),
        -float(debt.get("remaining_amount") or 0),
        _record_order(debt.get("id")),
    )


def build_basic_strategy(snapshot: dict, extra_monthly: float = 0) -> dict:
    income = _money(snapshot.get("monthly_income_estimate"))
    essentials = _money(snapshot.get("essential_monthly_expenses"))
    savings = _money(snapshot.get("liquid_savings"))
    emergency_target = _money(snapshot.get("emergency_fund_target"))
    debts = [dict(d) for d in snapshot.get("debts", []) if _money(d.get("remaining_amount")) > 0]
    minimums = sum(_money(d.get("monthly_payment")) for d in debts)
    extra_monthly = _money(extra_monthly)
    warnings: list[str] = []

    if income <= 0:
        return {
            "status": "needs_income", "priority": "income", "monthly_income": 0,
            "essential_expenses": essentials, "minimum_debt_payments": round(minimums, 2),
            "strategic_margin": 0, "allocations": [], "target_debt": None,
            "recommendation": tx("Completá tus ingresos para que DINCR pueda construir una estrategia mensual.", "Add your income so DINCR can build a monthly strategy."),
            "warnings": [tx("No hay un ingreso mensual estimable.", "There is no estimable monthly income.")], "projection": None,
        }

    if snapshot.get("essential_monthly_expenses") is None:
        warnings.append(tx("Tus gastos esenciales son desconocidos; completalos para mejorar la precisión.", "Your essential expenses are unknown; add them to improve accuracy."))
    missing_minimums = sum(1 for d in debts if d.get("monthly_payment") is None)
    if missing_minimums:
        warnings.append(tx(
            f"Falta la cuota mensual de {missing_minimums} {plural(missing_minimums, ('deuda', 'debt'), ('deudas', 'debts'))}; DINCR no la inventó.",
            f"The monthly payment is missing for {missing_minimums} {plural(missing_minimums, ('deuda', 'debt'), ('deudas', 'debts'))}; DINCR didn’t make it up.",
        ))
    missing_rates = sum(1 for d in debts if d.get("interest_rate") is None)
    if missing_rates:
        warnings.append(tx(
            f"Falta la tasa de interés de {missing_rates} {plural(missing_rates, ('deuda', 'debt'), ('deudas', 'debts'))}; la prioridad usa los datos disponibles.",
            f"The interest rate is missing for {missing_rates} {plural(missing_rates, ('deuda', 'debt'), ('deudas', 'debts'))}; the priority uses the available data.",
        ))

    base_margin = round(income - essentials - minimums, 2)
    if base_margin < 0:
        deficit = abs(base_margin)
        return {
            "status": "critical", "priority": "stabilize", "monthly_income": income,
            "essential_expenses": essentials, "minimum_debt_payments": round(minimums, 2),
            "strategic_margin": base_margin, "allocations": [], "target_debt": None,
            "recommendation": tx(
                f"Tus compromisos conocidos superan el ingreso estimado por {deficit:.2f}. Priorizá necesidades esenciales y pagos obligatorios antes de hacer abonos extraordinarios.",
                f"Your known commitments exceed estimated income by {deficit:.2f}. Prioritize essential needs and required payments before making extra payments.",
            ),
            "warnings": warnings, "projection": None,
        }

    available = round(base_margin + extra_monthly, 2)
    allocations = []
    starter_reserve_target = min(emergency_target if emergency_target > 0 else income * 0.10, max(income * 0.10, 1))
    reserve_gap = max(starter_reserve_target - savings, 0)
    reserve_allocation = min(available * 0.20, reserve_gap) if debts and reserve_gap > 0 else min(available, reserve_gap)
    reserve_allocation = round(reserve_allocation, 2)
    if reserve_allocation > 0:
        allocations.append({"bucket": "emergency", "label": tx("Reserva de emergencia", "Emergency reserve"), "amount": reserve_allocation})
        available = round(available - reserve_allocation, 2)

    target = max(debts, key=_debt_score) if debts else None
    projection = None
    if target and available > 0:
        allocations.append({"bucket": "debt_extra", "label": tx(f"Abono extra a {target['name']}", f"Extra payment to {target['name']}"), "amount": available, "debt_id": target.get("id")})
        normal = _money(target.get("monthly_payment"))
        months = _months_to_payoff(_money(target.get("remaining_amount")), normal + available, target.get("interest_rate"))
        baseline = _months_to_payoff(_money(target.get("remaining_amount")), normal, target.get("interest_rate"))
        projection = {"debt_id": target.get("id"), "name": target.get("name"), "months": months, "baseline_months": baseline, "monthly_to_target": round(normal + available, 2)}
        recommendation = tx(f"Cubrí tus compromisos y dirigí el excedente a {target['name']}.", f"Cover your commitments and send the surplus to {target['name']}.")
        priority = "debt"
    elif target:
        recommendation = tx("Cubrí gastos esenciales y cuotas conocidas. Este mes no hay margen seguro para un abono extraordinario.", "Cover essential expenses and known payments. This month there is no safe margin for an extra payment.")
        priority = "debt"
    else:
        if available > 0:
            allocations.append({"bucket": "emergency", "label": tx("Ahorro / fondo de emergencia", "Savings / emergency fund"), "amount": available})
        recommendation = tx("No tenés deuda activa. Usá el margen disponible para fortalecer tu fondo de emergencia.", "You have no active debt. Use the available margin to strengthen your emergency fund.")
        priority = "emergency"

    commitment_ratio = round(((essentials + minimums) / income) * 100, 1) if income else 0
    return {
        "status": "healthy" if base_margin > 0 else "tight", "priority": priority,
        "monthly_income": income, "essential_expenses": essentials,
        "minimum_debt_payments": round(minimums, 2), "strategic_margin": base_margin,
        "commitment_ratio": commitment_ratio, "allocations": allocations,
        "target_debt": target, "recommendation": recommendation, "warnings": warnings,
        "projection": projection, "simulation_extra": extra_monthly,
    }


def build_vip_strategy(snapshot: dict) -> dict:
    result = build_basic_strategy(snapshot)
    if result["status"] in {"needs_income", "critical"}:
        return {**result, "director_mode": True, "vip_allocations": result.get("allocations", []), "director_note": tx("Primero estabilizamos tu base financiera.", "First, we stabilize your financial base.")}

    preference = snapshot.get("strategy_preference") or "balanced"
    discretionary = _money(snapshot.get("discretionary_monthly_minimum"))
    margin = max(_money(result.get("strategic_margin")) - discretionary, 0)
    goals = [g for g in snapshot.get("goals", []) if _money(g.get("target_amount")) > _money(g.get("current_amount"))]
    savings = _money(snapshot.get("liquid_savings"))
    emergency_target = _money(snapshot.get("emergency_fund_target"))
    emergency_gap = max(emergency_target - savings, 0)
    debts = [d for d in snapshot.get("debts", []) if _money(d.get("remaining_amount")) > 0]
    target = max(debts, key=_debt_score) if debts else None

    weights = {
        "debt": (0.70, 0.20, 0.10),
        "emergency": (0.30, 0.60, 0.10),
        "goals": (0.30, 0.20, 0.50),
        "balanced": (0.50, 0.30, 0.20),
    }[preference]
    debt_w, emergency_w, goal_w = weights
    allocations = []
    if discretionary > 0:
        allocations.append({"bucket": "personal", "label": tx("Mínimo reservado para vos", "Minimum reserved for you"), "amount": min(discretionary, _money(result.get("strategic_margin")))})
    if target and margin > 0:
        allocations.append({"bucket": "debt_extra", "label": tx(f"Abono extra a {target['name']}", f"Extra payment to {target['name']}"), "amount": round(margin * debt_w, 2), "debt_id": target.get("id")})
    if emergency_gap > 0 and margin > 0:
        allocations.append({"bucket": "emergency", "label": tx("Fondo de emergencia", "Emergency fund"), "amount": round(min(margin * emergency_w, emergency_gap), 2)})
    if goals and margin > 0:
        priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        goal = sorted(goals, key=lambda g: (priority_rank.get(g.get("priority"), 2), str(g.get("target_date") or "9999-12-31"), -_record_order(g.get("id"))))[0]
        allocations.append({"bucket": "goal", "label": tx(f"Meta: {goal['name']}", f"Goal: {goal['name']}"), "amount": round(margin * goal_w, 2), "goal_id": goal.get("id")})

    allocated = round(sum(a["amount"] for a in allocations), 2)
    unallocated = round(max(_money(result.get("strategic_margin")) - allocated, 0), 2)
    if unallocated > 0:
        allocations.append({"bucket": "flex", "label": tx("Margen flexible", "Flexible margin"), "amount": unallocated})
    return {
        **result, "director_mode": True, "strategy_preference": preference,
        "vip_allocations": allocations,
        "director_note": tx("DINCR coordinó deuda, seguridad, metas y tu mínimo personal según la prioridad elegida.", "DINCR coordinated debt, safety, goals, and your personal minimum based on your chosen priority."),
    }


def _goal_monthly_need(goal: dict, reference_date=None) -> float | None:
    """Monthly amount needed to hit a dated goal; None when no usable date exists."""
    from datetime import date
    target_date = goal.get("target_date")
    if not target_date:
        return None
    try:
        target = date.fromisoformat(str(target_date))
    except ValueError:
        return None
    today = reference_date or date.today()
    months = max((target.year - today.year) * 12 + target.month - today.month, 1)
    gap = max(_money(goal.get("target_amount")) - _money(goal.get("current_amount")), 0)
    return round(gap / months, 2)


def build_vip_insights(snapshot: dict, strategy: dict | None = None) -> dict:
    """Director-level diagnostics derived only from known data; never invents missing values."""
    strategy = strategy or build_vip_strategy(snapshot)
    income = _money(snapshot.get("monthly_income_estimate"))
    essentials = snapshot.get("essential_monthly_expenses")
    savings = _money(snapshot.get("liquid_savings"))
    emergency_target = _money(snapshot.get("emergency_fund_target"))
    debts = [d for d in snapshot.get("debts", []) if _money(d.get("remaining_amount")) > 0]
    goals = [g for g in snapshot.get("goals", []) if _money(g.get("target_amount")) > _money(g.get("current_amount"))]

    emergency_months = None
    if essentials is not None and _money(essentials) > 0:
        emergency_months = round(savings / _money(essentials), 1)

    goal_guidance = []
    for goal in goals:
        gap = round(max(_money(goal.get("target_amount")) - _money(goal.get("current_amount")), 0), 2)
        monthly_need = _goal_monthly_need(goal)
        goal_guidance.append({
            "id": goal.get("id"), "name": goal.get("name"), "priority": goal.get("priority") or "medium",
            "remaining": gap, "target_date": goal.get("target_date"), "monthly_needed": monthly_need,
        })

    alerts = []
    if income <= 0:
        alerts.append({"level": "critical", "code": "income_missing", "message": tx("Falta un ingreso mensual estimable.", "An estimable monthly income is missing.")})
    if strategy.get("status") == "critical":
        alerts.append({"level": "critical", "code": "negative_margin", "message": tx("Los compromisos conocidos superan el ingreso mensual estimado.", "Known commitments exceed estimated monthly income.")})
    if debts and any(d.get("interest_rate") is None for d in debts):
        alerts.append({"level": "info", "code": "apr_missing", "message": tx("Hay deudas sin tasa registrada; completar ese dato mejora la priorización.", "Some debts have no recorded rate; adding it improves prioritization.")})
    if emergency_target > 0 and savings < emergency_target:
        pct = round((savings / emergency_target) * 100, 1) if emergency_target else 0
        alerts.append({"level": "warning", "code": "emergency_gap", "message": tx(f"Tu fondo de emergencia está al {pct}% del objetivo.", f"Your emergency fund is at {pct}% of the target.")})
    for goal in goal_guidance:
        if goal["monthly_needed"] is not None and goal["monthly_needed"] > max(_money(strategy.get("strategic_margin")), 0):
            alerts.append({"level": "warning", "code": f"goal_pressure_{goal['id']}", "message": tx(f"La meta {goal['name']} requiere más al mes que tu margen estratégico actual.", f"The goal {goal['name']} needs more each month than your current strategic margin.")})

    return {
        "emergency_months": emergency_months,
        "emergency_progress": round(min((savings / emergency_target) * 100, 100), 1) if emergency_target > 0 else None,
        "goal_guidance": goal_guidance,
        "alerts": alerts,
        "total_debt": round(sum(_money(d.get("remaining_amount")) for d in debts), 2),
        "active_goals": len(goals),
    }


def build_vip_scenario(snapshot: dict, monthly_income_change: float = 0, monthly_expense_change: float = 0,
                       one_time_extra: float = 0) -> dict:
    """Compare a hypothetical future against the current state without persisting anything."""
    base_snapshot = {**snapshot, "debts": [dict(d) for d in snapshot.get("debts", [])], "goals": [dict(g) for g in snapshot.get("goals", [])]}
    scenario_snapshot = {**base_snapshot}
    scenario_snapshot["monthly_income_estimate"] = max(_money(base_snapshot.get("monthly_income_estimate")) + float(monthly_income_change or 0), 0)
    current_essentials = base_snapshot.get("essential_monthly_expenses")
    scenario_snapshot["essential_monthly_expenses"] = max(_money(current_essentials) + float(monthly_expense_change or 0), 0) if current_essentials is not None else None
    scenario_snapshot["liquid_savings"] = _money(base_snapshot.get("liquid_savings")) + _money(one_time_extra)

    current = build_vip_strategy(base_snapshot)
    simulated = build_vip_strategy(scenario_snapshot)
    return {
        "current": current,
        "scenario": simulated,
        "delta": {
            "strategic_margin": round(_money(simulated.get("strategic_margin")) - _money(current.get("strategic_margin")), 2),
            "monthly_income": round(_money(simulated.get("monthly_income")) - _money(current.get("monthly_income")), 2),
            "essential_expenses": round(_money(simulated.get("essential_expenses")) - _money(current.get("essential_expenses")), 2),
        },
        "inputs": {"monthly_income_change": round(float(monthly_income_change or 0), 2), "monthly_expense_change": round(float(monthly_expense_change or 0), 2), "one_time_extra": _money(one_time_extra)},
    }


def build_paycheck_plan(strategy: dict, pay_frequency: str | None, vip: bool = False) -> dict:
    """Translate the monthly strategy into a practical next-paycheck envelope plan."""
    periods = {"weekly": 52 / 12, "biweekly": 26 / 12, "monthly": 1}.get(pay_frequency or "monthly", 1)
    income = round(_money(strategy.get("monthly_income")) / periods, 2)
    essentials = round(_money(strategy.get("essential_expenses")) / periods, 2)
    minimums = round(_money(strategy.get("minimum_debt_payments")) / periods, 2)
    source = strategy.get("vip_allocations" if vip else "allocations", [])
    envelopes = []
    if essentials > 0:
        envelopes.append({"bucket": "essentials", "label": tx("Gastos esenciales", "Essential expenses"), "amount": essentials})
    if minimums > 0:
        envelopes.append({"bucket": "debt_minimums", "label": tx("Cuotas de deuda", "Debt payments"), "amount": minimums})
    for allocation in source:
        amount = round(_money(allocation.get("amount")) / periods, 2)
        if amount > 0:
            envelopes.append({**allocation, "amount": amount})
    allocated = round(sum(_money(x.get("amount")) for x in envelopes), 2)
    return {
        "pay_frequency": pay_frequency or "monthly", "periods_per_month": round(periods, 4),
        "estimated_paycheck": income, "envelopes": envelopes,
        "unassigned": round(max(income - allocated, 0), 2),
    }
