from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any


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


def _debt_score(debt: dict) -> tuple:
    """Deterministic hybrid: known APR first, then due date and smaller balance."""
    rate = debt.get("interest_rate")
    known_rate = rate is not None
    return (
        1 if known_rate else 0,
        float(rate or 0),
        -(int(debt.get("payment_day") or 32)),
        -float(debt.get("remaining_amount") or 0),
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
            "recommendation": "Completá tus ingresos para que JARVIS pueda construir una estrategia mensual.",
            "warnings": ["No hay un ingreso mensual estimable."], "projection": None,
        }

    if snapshot.get("essential_monthly_expenses") is None:
        warnings.append("Tus gastos esenciales son desconocidos; completalos para mejorar la precisión.")
    missing_minimums = sum(1 for d in debts if d.get("monthly_payment") is None)
    if missing_minimums:
        warnings.append(f"Falta la cuota mensual de {missing_minimums} deuda(s); JARVIS no la inventó.")
    missing_rates = sum(1 for d in debts if d.get("interest_rate") is None)
    if missing_rates:
        warnings.append(f"Falta la tasa de interés de {missing_rates} deuda(s); la prioridad usa los datos disponibles.")

    base_margin = round(income - essentials - minimums, 2)
    if base_margin < 0:
        deficit = abs(base_margin)
        return {
            "status": "critical", "priority": "stabilize", "monthly_income": income,
            "essential_expenses": essentials, "minimum_debt_payments": round(minimums, 2),
            "strategic_margin": base_margin, "allocations": [], "target_debt": None,
            "recommendation": f"Tus compromisos conocidos superan el ingreso estimado por {deficit:.2f}. Priorizá necesidades esenciales y pagos obligatorios antes de hacer abonos extraordinarios.",
            "warnings": warnings, "projection": None,
        }

    available = round(base_margin + extra_monthly, 2)
    allocations = []
    starter_reserve_target = min(emergency_target if emergency_target > 0 else income * 0.10, max(income * 0.10, 1))
    reserve_gap = max(starter_reserve_target - savings, 0)
    reserve_allocation = min(available * 0.20, reserve_gap) if debts and reserve_gap > 0 else min(available, reserve_gap)
    reserve_allocation = round(reserve_allocation, 2)
    if reserve_allocation > 0:
        allocations.append({"bucket": "emergency", "label": "Reserva de emergencia", "amount": reserve_allocation})
        available = round(available - reserve_allocation, 2)

    target = max(debts, key=_debt_score) if debts else None
    projection = None
    if target and available > 0:
        allocations.append({"bucket": "debt_extra", "label": f"Abono extra a {target['name']}", "amount": available, "debt_id": target.get("id")})
        normal = _money(target.get("monthly_payment"))
        months = _months_to_payoff(_money(target.get("remaining_amount")), normal + available, target.get("interest_rate"))
        baseline = _months_to_payoff(_money(target.get("remaining_amount")), normal, target.get("interest_rate"))
        projection = {"debt_id": target.get("id"), "name": target.get("name"), "months": months, "baseline_months": baseline, "monthly_to_target": round(normal + available, 2)}
        recommendation = f"Cubrí tus compromisos y dirigí el excedente a {target['name']}."
        priority = "debt"
    elif target:
        recommendation = "Cubrí gastos esenciales y cuotas conocidas. Este mes no hay margen seguro para un abono extraordinario."
        priority = "debt"
    else:
        if available > 0:
            allocations.append({"bucket": "emergency", "label": "Ahorro / fondo de emergencia", "amount": available})
        recommendation = "No tenés deuda activa. Usá el margen disponible para fortalecer tu fondo de emergencia."
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
        return {**result, "director_mode": True, "vip_allocations": result.get("allocations", []), "director_note": "Primero estabilizamos tu base financiera."}

    preference = snapshot.get("strategy_preference") or "balanced"
    discretionary = _money(snapshot.get("discretionary_monthly_minimum"))
    margin = max(_money(result.get("strategic_margin")) - discretionary, 0)
    goals = [g for g in snapshot.get("goals", []) if _money(g.get("target_amount")) > _money(g.get("current_amount"))]
    savings = _money(snapshot.get("liquid_savings"))
    emergency_target = _money(snapshot.get("emergency_fund_target"))
    emergency_gap = max(emergency_target - savings, 0)
    debts = snapshot.get("debts", [])
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
        allocations.append({"bucket": "personal", "label": "Mínimo reservado para vos", "amount": min(discretionary, _money(result.get("strategic_margin")))})
    if target and margin > 0:
        allocations.append({"bucket": "debt_extra", "label": f"Abono extra a {target['name']}", "amount": round(margin * debt_w, 2), "debt_id": target.get("id")})
    if emergency_gap > 0 and margin > 0:
        allocations.append({"bucket": "emergency", "label": "Fondo de emergencia", "amount": round(min(margin * emergency_w, emergency_gap), 2)})
    if goals and margin > 0:
        priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        goal = sorted(goals, key=lambda g: (priority_rank.get(g.get("priority"), 2), str(g.get("target_date") or "9999-12-31")))[0]
        allocations.append({"bucket": "goal", "label": f"Meta: {goal['name']}", "amount": round(margin * goal_w, 2), "goal_id": goal.get("id")})

    allocated = round(sum(a["amount"] for a in allocations), 2)
    unallocated = round(max(_money(result.get("strategic_margin")) - allocated, 0), 2)
    if unallocated > 0:
        allocations.append({"bucket": "flex", "label": "Margen flexible", "amount": unallocated})
    return {
        **result, "director_mode": True, "strategy_preference": preference,
        "vip_allocations": allocations,
        "director_note": "JARVIS coordinó deuda, seguridad, metas y tu mínimo personal según la prioridad elegida.",
    }
