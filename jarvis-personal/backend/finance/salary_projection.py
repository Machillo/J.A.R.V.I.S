"""The Owner's monthly salary projection, as pure arithmetic (no database, no session).

One formula for every place that projects the salary: JARVIS (``service.calculate_monthly_salary_projection``,
the month in course) and the Owner's monthly ledger (``user_product/owner_ledger.py``, any month).

- Base: with an employment profile, hourly rate × weekly hours × 4.333 minus the configured
  deductions (percentage on the gross, fixed by frequency); without one, the saved net base salary.
- The month's overtime and bonuses are added net of the percentage deductions; VGH (negative,
  time not worked) subtracts its gross directly.
"""
from __future__ import annotations


def as_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def monthly_amount_from_frequency(amount: float, frequency: str | None) -> float:
    frequency = (frequency or 'monthly').lower().strip()
    amount = as_float(amount)
    if frequency == 'weekly':
        return amount * 4.333
    if frequency in {'biweekly', 'cada_2_semanas', 'quincenal'}:
        return amount * 2.166
    if frequency == 'annual':
        return amount / 12
    return amount


def variable_payroll_deductions(gross_amount: float, deductions: list[dict]) -> tuple[float, list[dict]]:
    """Rebajos aplicables a OT/bonos/VGH.

    Si el salario base mensual ya está guardado como neto, no repetimos rebajos fijos
    semanales sobre el salario base. Para ingresos extra aplicamos solo rebajos
    porcentuales configurados.
    """
    total = 0.0
    details = []
    for deduction in deductions:
        deduction_type = str(deduction.get('deduction_type') or '').lower().strip()
        amount = as_float(deduction.get('amount'))
        if deduction_type == 'percentage':
            calculated = gross_amount * (amount / 100)
            total += calculated
            details.append({
                'name': deduction.get('name'),
                'deduction_type': deduction_type,
                'base_amount': amount,
                'frequency': deduction.get('frequency'),
                'calculated_monthly_amount': calculated,
                'applies_to': 'extra_income',
            })
    return total, details


def project(profile: dict | None, deductions: list[dict], payroll_events: list[dict], bonuses: list[dict],
            base_salary_net: float) -> dict:
    """The month's projection from its inputs; the same figures JARVIS has always shown."""
    if profile:
        hourly_rate = as_float(profile.get("hourly_rate"))
        weekly_hours = as_float(profile.get("regular_hours_per_week"))
        base_monthly_gross = hourly_rate * weekly_hours * 4.333
    else:
        hourly_rate = 0.0
        weekly_hours = 0.0
        base_monthly_gross = base_salary_net

    # Si hay perfil laboral, el salario base se calcula desde hourly_rate y rebajos reales.
    # La tabla salaries solo se usa como respaldo si no hay perfil laboral.
    fixed_deduction_details = []
    fixed_deductions_total = 0.0
    if base_salary_net > 0 and not profile:
        base_monthly_net = base_salary_net
    else:
        for deduction in deductions:
            amount = as_float(deduction.get("amount"))
            deduction_type = str(deduction.get("deduction_type") or "").lower().strip()
            if deduction_type == "percentage":
                calculated = base_monthly_gross * (amount / 100)
            else:
                calculated = monthly_amount_from_frequency(amount, deduction.get("frequency"))
            fixed_deductions_total += calculated
            fixed_deduction_details.append({
                "name": deduction.get("name"),
                "deduction_type": deduction_type or "fixed",
                "base_amount": amount,
                "frequency": deduction.get("frequency"),
                "calculated_monthly_amount": calculated,
                "applies_to": "base_salary",
            })
        base_monthly_net = max(base_monthly_gross - fixed_deductions_total, 0)

    positive_payroll_gross = sum(max(as_float(event.get("amount")), 0) for event in payroll_events)
    vgh_gross = sum(min(as_float(event.get("amount")), 0) for event in payroll_events)
    bonuses_gross = sum(as_float(item.get("amount")) for item in bonuses)

    extra_base = positive_payroll_gross + max(bonuses_gross, 0)
    extra_deductions_total, extra_deduction_details = variable_payroll_deductions(extra_base, deductions)

    if extra_base > 0:
        payroll_extra_deduction = extra_deductions_total * (positive_payroll_gross / extra_base)
        bonus_deduction = extra_deductions_total * (max(bonuses_gross, 0) / extra_base)
    else:
        payroll_extra_deduction = 0.0
        bonus_deduction = 0.0

    # VGH es tiempo no trabajado: resta bruto directo y no recibe rebajo positivo.
    payroll_events_gross = positive_payroll_gross + vgh_gross
    payroll_events_net = (positive_payroll_gross - payroll_extra_deduction) + vgh_gross
    bonuses_net = bonuses_gross - bonus_deduction if bonuses_gross > 0 else bonuses_gross

    projected_gross = base_monthly_gross + payroll_events_gross + bonuses_gross
    projected_net = base_monthly_net + payroll_events_net + bonuses_net

    return {
        "status": "OK" if (base_monthly_net > 0 or profile) else "MISSING_BASE_SALARY",
        "base": {
            "hourly_rate": hourly_rate,
            "regular_hours_per_week": weekly_hours,
            "base_monthly_gross": round(base_monthly_gross, 2),
            "base_monthly_net": round(base_monthly_net, 2),
            "base_salary_source": "salaries" if base_salary_net > 0 else "employment_profile",
        },
        "adjustments": {
            "payroll_events_total": round(payroll_events_gross, 2),
            "payroll_events_net": round(payroll_events_net, 2),
            "bonuses_gross": round(bonuses_gross, 2),
            "bonuses_net": round(bonuses_net, 2),
            "projected_gross": round(projected_gross, 2),
            "events": payroll_events,
            "bonuses": bonuses,
        },
        "deductions": {
            "total_deductions": round(fixed_deductions_total + extra_deductions_total, 2),
            "fixed_deductions_total": round(fixed_deductions_total, 2),
            "extra_deductions_total": round(extra_deductions_total, 2),
            "details": fixed_deduction_details + extra_deduction_details,
        },
        "results": {
            "base_net": round(base_monthly_net, 2),
            "projected_net": round(projected_net, 2),
            "current_month_adjustments_net": round(projected_net - base_monthly_net, 2),
            "current_month_adjustments_gross": round(payroll_events_gross + bonuses_gross, 2),
        },
    }
