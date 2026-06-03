from backend.finance.service import get_user_status, get_net_worth_report
from backend.transactions.analyzer import get_transaction_analysis


def get_financial_advice():
    user_status = get_user_status()
    net_worth = get_net_worth_report()
    transactions = get_transaction_analysis()

    advice = []
    warnings = []
    priorities = []

    available_cash = user_status["cashflow"]["available_cash"]
    debt_total = user_status["debts"]["total"]
    monthly_debt_payments = user_status["debts"]["monthly_payments"]
    income = user_status["income"]["monthly_net_income"]
    goals = user_status["goals"]

    # Riesgo financiero general
    if net_worth["status"] == "negative":
        warnings.append(
            "Tu patrimonio neto sigue negativo. Tus deudas superan tus activos registrados."
        )

    if user_status["financial_health"]["risk_level"] == "high":
        priorities.append(
            "Priorizar reducción de deuda y registrar activos reales."
        )

    # Cashflow
    if available_cash < 50000:
        warnings.append(
            "Tu efectivo disponible estimado es muy bajo. Cualquier gasto grande puede desbalancearte."
        )
    elif available_cash < 100000:
        warnings.append(
            "Tu efectivo disponible estimado está ajustado. Conviene controlar ocio y compras variables."
        )
    else:
        advice.append(
            "Tienes algo de margen disponible, pero debe distribuirse entre deuda, metas y emergencias."
        )

    # Deuda vs ingreso
    debt_payment_ratio = (
        monthly_debt_payments / income
        if income > 0 else None
    )

    if debt_payment_ratio is not None:
        if debt_payment_ratio >= 0.35:
            warnings.append(
                "Tus pagos mensuales de deuda consumen una parte alta de tu ingreso."
            )
            priorities.append(
                "Buscar reducir cuotas o atacar deudas con mayor interés."
            )
        elif debt_payment_ratio >= 0.25:
            advice.append(
                "Tus pagos de deuda son manejables, pero todavía limitan tu capacidad de ahorro."
            )

    # Deudas de alto interés
    high_interest_debts = net_worth["liabilities"]["high_interest_debts"]

    if high_interest_debts:
        names = ", ".join(debt["name"] for debt in high_interest_debts)
        priorities.append(
            f"Revisar deudas de alto interés: {names}."
        )

    # Metas
    if goals["critical_goals_count"] > 0:
        goal = goals["most_urgent_goal"]
        priorities.append(
            f"Meta crítica activa: {goal['name']}. Falta ₡{goals['total_goals_remaining']:,.2f}."
        )

    # Gasto por categorías
    top_categories = transactions.get("top_expense_categories", [])

    if top_categories:
        biggest_category = top_categories[0]

        advice.append(
            f"Tu categoría de gasto más alta es {biggest_category['category']} con ₡{biggest_category['total']:,.2f}."
        )

    # Score simple
    score = 100

    if net_worth["status"] == "negative":
        score -= 25

    if available_cash < 100000:
        score -= 15

    if debt_payment_ratio and debt_payment_ratio >= 0.35:
        score -= 20
    elif debt_payment_ratio and debt_payment_ratio >= 0.25:
        score -= 10

    if goals["critical_goals_count"] > 0:
        score -= 10

    if high_interest_debts:
        score -= 10

    score = max(score, 0)

    if score >= 80:
        health_label = "stable"
    elif score >= 60:
        health_label = "watch"
    elif score >= 40:
        health_label = "stressed"
    else:
        health_label = "critical"

    return {
        "financial_score": score,
        "health_label": health_label,
        "summary": {
            "available_cash": available_cash,
            "net_worth": user_status["assets"]["net_worth"],
            "debt_total": debt_total,
            "monthly_debt_payments": monthly_debt_payments,
            "debt_payment_ratio": debt_payment_ratio,
            "main_goal": goals["most_urgent_goal"],
        },
        "warnings": warnings,
        "priorities": priorities,
        "advice": advice,
        "data_sources": {
            "user_status": "/finance/user-status",
            "net_worth": "/finance/net-worth",
            "transactions": "/transactions/analysis/summary"
        }
    }

def analyze_spending_habits():
    transactions = get_transaction_analysis()

    fixed_categories = [
        "Vivienda",
        "Casa",
        "Servicios",
        "Seguros"
    ]

    variable_categories = []
    fixed_expenses = []

    top_categories = transactions.get("top_expense_categories", [])
    expenses_by_month = transactions.get("expenses_by_month", [])
    category_months = transactions.get("expenses_by_category_and_month", [])

    for category in top_categories:
        if category["category"] in fixed_categories:
            fixed_expenses.append(category)
        else:
            variable_categories.append(category)

    highest_variable_category = (
        variable_categories[0]
        if variable_categories
        else None
    )

    monthly_totals = [
        item["total"]
        for item in expenses_by_month
        if item["month"].startswith("2026")
    ]

    average_monthly_spending = (
        sum(monthly_totals) / len(monthly_totals)
        if monthly_totals
        else 0
    )

    unusual_months = []

    for item in expenses_by_month:
        if not item["month"].startswith("2026"):
            continue

        if average_monthly_spending > 0 and item["total"] > average_monthly_spending * 1.25:
            unusual_months.append({
                "month": item["month"],
                "total": item["total"],
                "reason": "Gasto superior al promedio mensual por más de 25%."
            })

    recurring_categories = {}

    for item in category_months:
        category = item["category"]
        month = item["month"]

        if not month.startswith("2026"):
            continue

        if category not in recurring_categories:
            recurring_categories[category] = {
                "category": category,
                "months_present": set(),
                "total": 0
            }

        recurring_categories[category]["months_present"].add(month)
        recurring_categories[category]["total"] += item["total"]

    recurring_summary = []

    for category, data in recurring_categories.items():
        recurring_summary.append({
            "category": category,
            "months_count": len(data["months_present"]),
            "total": data["total"],
            "average_when_present": (
                data["total"] / len(data["months_present"])
                if data["months_present"]
                else 0
            )
        })

    recurring_summary.sort(
        key=lambda item: item["months_count"],
        reverse=True
    )

    insights = []
    warnings = []
    opportunities = []

    if highest_variable_category:
        insights.append(
            f"Tu gasto variable más alto es {highest_variable_category['category']} con ₡{highest_variable_category['total']:,.2f}."
        )

    if unusual_months:
        warnings.append(
            "Hay meses con gasto superior al promedio. Conviene revisar qué eventos causaron esos picos."
        )

    for category in variable_categories[:3]:
        opportunities.append(
            f"Revisar presupuesto de {category['category']}."
        )

    if average_monthly_spending > 0:
        insights.append(
            f"Tu gasto mensual promedio registrado en 2026 es ₡{average_monthly_spending:,.2f}."
        )

    return {
        "average_monthly_spending": average_monthly_spending,
        "highest_variable_category": highest_variable_category,
        "fixed_expenses_detected": fixed_expenses,
        "top_variable_categories": variable_categories[:5],
        "unusual_months": unusual_months,
        "recurring_categories": recurring_summary[:10],
        "insights": insights,
        "warnings": warnings,
        "opportunities": opportunities
    }