from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from statistics import pstdev
from typing import Any

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.user_product.basic_service import (
    _ensure_basic_schema,
    _estimated_income,
    _ledger_totals,
    _monthly_equivalent,
    _next_month,
    _profile,
    _shift_month,
)


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{table}",)).fetchone()["exists"])


def _payoff(balance: float, payment: float, annual_rate: float) -> dict:
    balance, payment, rate = max(balance, 0), max(payment, 0), max(annual_rate, 0) / 1200
    if not balance:
        return {"months": 0, "interest": 0}
    if not payment or (rate and payment <= balance * rate):
        return {"months": None, "interest": None}
    original, interest = balance, 0.0
    for month in range(1, 1201):
        charge = balance * rate
        interest += charge
        balance = balance + charge - payment
        if balance <= 0.01:
            return {"months": month, "interest": round(interest, 2), "principal": original}
    return {"months": None, "interest": None}


def _debt_plan(debts: list[dict], extra: float, method: str) -> dict:
    active = [dict(row) for row in debts if _money(row.get("remaining_amount")) > 0]
    if method == "snowball":
        ordered = sorted(active, key=lambda row: (_money(row.get("remaining_amount")), -_money(row.get("interest_rate"))))
    elif method == "avalanche":
        ordered = sorted(active, key=lambda row: (-_money(row.get("interest_rate")), _money(row.get("remaining_amount"))))
    else:
        ordered = sorted(active, key=lambda row: (-_money(row.get("interest_rate")) * .7, _money(row.get("remaining_amount")) * .3))
    target = ordered[0] if ordered else None
    payment = _money(target.get("monthly_payment")) + max(extra, 0) if target else 0
    projection = _payoff(_money(target.get("remaining_amount")), payment, _money(target.get("interest_rate"))) if target else {"months": 0, "interest": 0}
    return {
        "method": method,
        "target": target.get("name") if target else None,
        "target_id": target.get("id") if target else None,
        "monthly_to_target": round(payment, 2),
        **projection,
    }


def get_vip_command_center() -> dict:
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    today = date.today()
    current = today.replace(day=1)
    with get_connection() as conn:
        _ensure_basic_schema(conn)
        profile = _profile(conn, account_id, workspace_id)
        debts = [dict(row) for row in conn.execute(
            """SELECT id,name,remaining_amount,total_amount,monthly_payment,NULLIF(interest_rate,0) interest_rate,
                      payment_day,next_payment_date FROM debts WHERE workspace_id=%s AND remaining_amount>0 ORDER BY id""",
            (workspace_id,),
        ).fetchall()]
        goals = [dict(row) for row in conn.execute(
            """SELECT id,name,target_amount,current_amount,target_date,priority FROM financial_goals
               WHERE workspace_id=%s AND status='active' ORDER BY target_date NULLS LAST,id""",
            (workspace_id,),
        ).fetchall()]
        accounts = []
        if _table_exists(conn, "account_balances"):
            accounts = [dict(row) for row in conn.execute(
                """SELECT account_name,bank_name,currency,current_balance,account_type,include_in_net_worth
                   FROM account_balances WHERE workspace_id=%s AND is_active=TRUE""",
                (workspace_id,),
            ).fetchall()]
        months = []
        for offset in range(-11, 1):
            start = _shift_month(current, offset)
            totals = _ledger_totals(conn, workspace_id, start, _next_month(start))
            months.append({"month": start.strftime("%Y-%m"), **totals, "balance": round(totals["income"] - totals["expenses"] - totals["debt_paid"], 2)})
        recurring = [dict(row) for row in conn.execute(
            "SELECT id,name,amount,category,item_type,frequency,due_day,is_active FROM finva_recurring_items WHERE workspace_id=%s AND is_active=TRUE ORDER BY amount DESC",
            (workspace_id,),
        ).fetchall()]
        detected_recurring = [dict(row) for row in conn.execute(
            """SELECT LEFT(regexp_replace(lower(description),'[^a-z0-9]+',' ','g'),60) AS merchant,
                      ROUND(AVG(amount),2) AS average_amount,MIN(amount) AS minimum_amount,MAX(amount) AS maximum_amount,
                      COUNT(DISTINCT date_trunc('month',transaction_date::date)) AS months_seen
               FROM transactions
               WHERE workspace_id=%s AND transaction_type='expense'
                 AND transaction_date::date >= %s AND COALESCE(description,'')<>''
               GROUP BY 1
               HAVING COUNT(DISTINCT date_trunc('month',transaction_date::date))>=2
               ORDER BY months_seen DESC,average_amount DESC LIMIT 12""",
            (workspace_id, _shift_month(current, -5)),
        ).fetchall()]
        candidates = {"confirmed": 0, "review": 0, "duplicates": 0}
        if _table_exists(conn, "email_transaction_candidates"):
            rows = conn.execute(
                "SELECT status,COUNT(*) total FROM email_transaction_candidates WHERE workspace_id=%s GROUP BY status",
                (workspace_id,),
            ).fetchall()
            counts = {str(row["status"]): int(row["total"]) for row in rows}
            candidates = {
                "confirmed": counts.get("confirmed", 0) + counts.get("auto_saved", 0),
                "review": counts.get("pending", 0) + counts.get("needs_review", 0),
                "duplicates": counts.get("duplicate", 0),
            }

    estimated_income = _estimated_income(profile)
    positive_incomes = [_money(row["income"]) for row in months if _money(row["income"]) > 0]
    conservative_income = round(min(estimated_income or float("inf"), sum(positive_incomes[-3:]) / len(positive_incomes[-3:]) if positive_incomes else estimated_income or 0), 2)
    if conservative_income == float("inf"):
        conservative_income = 0
    variability = round(pstdev(positive_incomes[-6:]) / (sum(positive_incomes[-6:]) / len(positive_incomes[-6:])) * 100, 1) if len(positive_incomes[-6:]) > 1 and sum(positive_incomes[-6:]) else 0
    essentials = _money(profile.get("essential_monthly_expenses"))
    savings = _money(profile.get("liquid_savings"))
    emergency_target = _money(profile.get("emergency_fund_target"))
    debt_balance = round(sum(_money(row.get("remaining_amount")) for row in debts), 2)
    debt_minimums = round(sum(_money(row.get("monthly_payment")) for row in debts), 2)
    recurring_expense = round(sum(_monthly_equivalent(_money(row["amount"]), row["frequency"]) for row in recurring if row["item_type"] == "expense"), 2)
    recurring_income = round(sum(_monthly_equivalent(_money(row["amount"]), row["frequency"]) for row in recurring if row["item_type"] == "income"), 2)
    monthly_income = conservative_income + recurring_income
    known_commitments = max(essentials, recurring_expense) + debt_minimums
    margin = round(monthly_income - known_commitments, 2)
    emergency_gap = max(emergency_target - savings, 0)
    all_assets = round(sum(_money(row["current_balance"]) for row in accounts if row.get("include_in_net_worth") and row.get("currency") == "CRC"), 2)
    liquid_assets = all_assets if accounts else savings
    net_worth = round(all_assets - debt_balance, 2)

    coverage = savings / known_commitments if known_commitments else 0
    debt_ratio = debt_minimums / monthly_income if monthly_income else 1
    cashflow_ratio = max(min((margin / monthly_income) if monthly_income else -1, 1), -1)
    completeness = sum([monthly_income > 0, essentials > 0 or recurring_expense > 0, all(row.get("monthly_payment") for row in debts) if debts else True, bool(accounts), emergency_target > 0]) / 5
    score = round(max(0, min(100, 45 + cashflow_ratio * 25 + min(coverage / 3, 1) * 20 - min(debt_ratio, 1) * 25 + completeness * 15)))
    score_factors = [
        {"label": "Flujo mensual", "impact": "positive" if margin >= 0 else "negative", "value": margin},
        {"label": "Cobertura de reserva", "impact": "positive" if coverage >= 1 else "warning", "value": round(coverage, 1)},
        {"label": "Carga de deuda", "impact": "negative" if debt_ratio > .35 else "positive", "value": round(debt_ratio * 100, 1)},
        {"label": "Calidad de datos", "impact": "positive" if completeness >= .8 else "warning", "value": round(completeness * 100)},
    ]

    priority = "stabilize" if margin < 0 else "emergency" if emergency_gap > 0 else "debt" if debts else "goals" if goals else "invest"
    labels = {"stabilize": "Cerrar el déficit mensual", "emergency": "Completar el fondo de emergencia", "debt": f"Atacar {max(debts, key=lambda x: _money(x.get('interest_rate'))).get('name')}" if debts else "Deuda", "goals": "Financiar la meta prioritaria", "invest": "Preparar inversión"}
    action_amount = abs(margin) if margin < 0 else min(max(margin, 0), emergency_gap) if priority == "emergency" else max(margin, 0)

    alerts = []
    if margin < 0:
        alerts.append({"severity": "critical", "title": "Cierre mensual negativo", "context": f"Faltan ₡{abs(margin):,.0f} para cubrir compromisos conocidos.", "action": "Reducí variables o aumentá ingreso antes de asumir otra obligación."})
    if coverage < 1:
        alerts.append({"severity": "high", "title": "Reserva menor a un mes", "context": f"La cobertura estimada es {coverage:.1f} meses.", "action": "Protegé el siguiente excedente en el fondo de emergencia."})
    if variability > 20:
        alerts.append({"severity": "medium", "title": "Ingreso variable", "context": f"La variación reciente es {variability}%.", "action": "Presupuestá con el ingreso conservador, no con el mejor mes."})
    if candidates["review"]:
        alerts.append({"severity": "medium", "title": "Movimientos por revisar", "context": f"Hay {candidates['review']} movimientos importados sin confirmar.", "action": "Revisalos antes de confiar en el cierre mensual."})
    increases = [row for row in detected_recurring if _money(row.get("minimum_amount")) and _money(row.get("maximum_amount")) > _money(row.get("minimum_amount")) * 1.10]
    if increases:
        alerts.append({"severity": "medium", "title": "Recurrente con variación", "context": f"{increases[0]['merchant']} cambió más de 10% entre cobros.", "action": "Confirmá si fue un aumento, consumo variable o cargo incorrecto."})

    goal_guidance = []
    for goal in goals:
        remaining = max(_money(goal["target_amount"]) - _money(goal["current_amount"]), 0)
        target = goal.get("target_date")
        months_left = max((target.year - today.year) * 12 + target.month - today.month, 1) if isinstance(target, date) else None
        required = round(remaining / months_left, 2) if months_left else None
        goal_guidance.append({**goal, "remaining": remaining, "months_left": months_left, "monthly_required": required, "viable": required is not None and required <= max(margin, 0), "alternative_months": ceil(remaining / max(margin, 1)) if margin > 0 else None})

    strategies = [_debt_plan(debts, max(margin, 0), method) for method in ("avalanche", "snowball", "finva")]
    best = min((row for row in strategies if row["months"] is not None), key=lambda row: (row["interest"], row["months"]), default=None)

    events = []
    start = today.replace(day=1)
    # Build the 45-day timeline from already loaded obligations to avoid hidden writes.
    for row in recurring:
        if row.get("due_day"):
            for shift in range(0, 2):
                month = _shift_month(start, shift); candidate = date(month.year, month.month, min(int(row["due_day"]), 28))
                if today <= candidate <= today + timedelta(days=45):
                    events.append({"date": candidate.isoformat(), "kind": row["item_type"], "label": row["name"], "amount": _money(row["amount"])})
    for row in debts:
        candidate = row.get("next_payment_date")
        if candidate:
            candidate = candidate if isinstance(candidate, date) else date.fromisoformat(str(candidate)[:10])
        elif row.get("payment_day"):
            candidate = date(today.year, today.month, min(int(row["payment_day"]), 28))
            if candidate < today:
                nxt = _next_month(today.replace(day=1)); candidate = date(nxt.year, nxt.month, min(int(row["payment_day"]), 28))
        if candidate and today <= candidate <= today + timedelta(days=45):
            events.append({"date": candidate.isoformat(), "kind": "debt", "label": row["name"], "amount": _money(row["monthly_payment"])})
    balance = liquid_assets
    timeline = []
    for event in sorted(events, key=lambda row: row["date"]):
        balance += event["amount"] if event["kind"] == "income" else -event["amount"]
        timeline.append({**event, "projected_balance": round(balance, 2)})
    safe_to_spend = round(max(min(margin, min([row["projected_balance"] for row in timeline], default=liquid_assets)), 0), 2)

    projection = []
    for months_ahead in (1, 3, 6, 12):
        projected_cash = round(liquid_assets + margin * months_ahead, 2)
        projected_debt = round(max(debt_balance - debt_minimums * months_ahead, 0), 2)
        projection.append({"months": months_ahead, "cash": projected_cash, "debt": projected_debt, "net_worth": round(projected_cash - projected_debt, 2), "confidence": "medium" if positive_incomes else "low"})

    roadmap = []
    if margin < 0:
        roadmap.append({"order": 1, "title": "Eliminar déficit", "amount": abs(margin), "why": "Sin flujo positivo no hay dinero seguro para deuda, metas o inversión."})
    if emergency_gap > 0:
        roadmap.append({"order": len(roadmap)+1, "title": "Completar reserva", "amount": min(max(margin, 0), emergency_gap), "why": "Protege tus obligaciones ante un imprevisto."})
    if best and margin > 0:
        roadmap.append({"order": len(roadmap)+1, "title": f"Abonar a {best['target']}", "amount": margin, "why": "Es el uso de menor costo financiero según saldo y tasa conocidos."})
    if goals and margin > 0:
        roadmap.append({"order": len(roadmap)+1, "title": f"Financiar {goals[0]['name']}", "amount": min(margin, goal_guidance[0].get("monthly_required") or margin), "why": "Alinea el aporte con fecha y prioridad."})
    investing_allowed = margin > 0 and emergency_gap <= 0 and debt_ratio <= .30
    roadmap.append({"order": len(roadmap)+1, "title": "Invertir" if investing_allowed else "Esperar para invertir", "amount": margin if investing_allowed else 0, "why": "Primero deben estar protegidos el flujo, la reserva y la deuda cara."})

    return {
        "as_of": today.isoformat(),
        "director": {"priority": priority, "headline": labels[priority], "next_action": f"Asigná ₡{action_amount:,.0f} a esta prioridad.", "data_complete": completeness >= .8},
        "score": {"value": score, "label": "Fuerte" if score >= 75 else "En progreso" if score >= 50 else "Vulnerable", "factors": score_factors},
        "goals": goal_guidance,
        "debt_planner": {"strategies": strategies, "recommended": best},
        "safe_to_spend": {"amount": safe_to_spend, "monthly_margin": margin, "next_45_days_minimum": min([row["projected_balance"] for row in timeline], default=liquid_assets)},
        "alerts": alerts,
        "calendar": timeline,
        "projections": projection,
        "net_worth": {"assets": all_assets, "liabilities": debt_balance, "value": net_worth, "accounts": accounts},
        "recurring": {"items": recurring, "detected": detected_recurring, "monthly_expenses": recurring_expense, "annual_expenses": round(recurring_expense*12, 2)},
        "reports": {"months": months, "current": months[-1], "previous": months[-2]},
        "variable_income": {"estimated": estimated_income, "conservative": conservative_income, "variability_percent": variability, "months_observed": len(positive_incomes)},
        "automation": candidates,
        "roadmap": roadmap,
        "assumptions": ["Montos en CRC para cálculos consolidados.", "Proyecciones usan ingreso conservador y obligaciones conocidas.", "Los escenarios no modifican datos reales."],
    }
