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

    category_groups = {
        "essential": [
            "Vivienda",
            "Casa",
            "Servicios",
            "Seguros",
            "Salud"
        ],
        "growth_aligned": [
            "Fitness",
            "Educación",
            "Gym"
        ],
        "controllable": [
            "Alimentación",
            "Restaurantes",
            "Compras Personales",
            "Videojuegos",
            "Streaming",
            "Apps",
            "Entretenimiento",
            "Transporte",
            "Cuidado Personal"
        ],
        "extraordinary": [
            "Regalos",
            "Compras Familiares",
            "Auto"
        ]
    }

    def classify_category(category_name: str):
        for group, categories in category_groups.items():
            if category_name in categories:
                return group

        return "uncategorized"

    top_categories = transactions.get("top_expense_categories", [])
    expenses_by_month = transactions.get("expenses_by_month", [])
    category_months = transactions.get("expenses_by_category_and_month", [])

    grouped_totals = {
        "essential": 0,
        "growth_aligned": 0,
        "controllable": 0,
        "extraordinary": 0,
        "uncategorized": 0
    }

    categorized_expenses = []

    for category in top_categories:
        group = classify_category(category["category"])

        grouped_totals[group] += category["total"]

        categorized_expenses.append({
            "category": category["category"],
            "total": category["total"],
            "impact_group": group
        })

    controllable_categories = [
        item for item in categorized_expenses
        if item["impact_group"] == "controllable"
    ]

    essential_categories = [
        item for item in categorized_expenses
        if item["impact_group"] == "essential"
    ]

    growth_categories = [
        item for item in categorized_expenses
        if item["impact_group"] == "growth_aligned"
    ]

    extraordinary_categories = [
        item for item in categorized_expenses
        if item["impact_group"] == "extraordinary"
    ]

    highest_controllable_category = (
        controllable_categories[0]
        if controllable_categories
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
        months_count = len(data["months_present"])
        impact_group = classify_category(category)

        recurring_summary.append({
            "category": category,
            "impact_group": impact_group,
            "months_count": months_count,
            "total": data["total"],
            "average_when_present": (
                data["total"] / months_count
                if months_count
                else 0
            )
        })

    recurring_summary.sort(
        key=lambda item: (
            item["months_count"],
            item["total"]
        ),
        reverse=True
    )

    insights = []
    warnings = []
    opportunities = []

    if highest_controllable_category:
        insights.append(
            f"Tu gasto controlable más alto es {highest_controllable_category['category']} con ₡{highest_controllable_category['total']:,.2f}."
        )

    if grouped_totals["growth_aligned"] > 0:
        insights.append(
            f"Tus gastos alineados a crecimiento personal suman ₡{grouped_totals['growth_aligned']:,.2f}."
        )

    if grouped_totals["extraordinary"] > 0:
        insights.append(
            f"Tus gastos extraordinarios suman ₡{grouped_totals['extraordinary']:,.2f}; conviene separarlos de tu gasto mensual normal."
        )

    if unusual_months:
        warnings.append(
            "Hay meses con gasto superior al promedio. Conviene revisar si fueron gastos extraordinarios o descontrol."
        )

    if highest_controllable_category:
        opportunities.append(
            f"Primera oportunidad de ajuste: revisar {highest_controllable_category['category']}."
        )

    for category in controllable_categories[1:4]:
        opportunities.append(
            f"Seguir monitoreando {category['category']}."
        )

    if average_monthly_spending > 0:
        insights.append(
            f"Tu gasto mensual promedio registrado en 2026 es ₡{average_monthly_spending:,.2f}."
        )

    return {
        "average_monthly_spending": average_monthly_spending,
        "impact_groups": {
            "essential": {
                "total": grouped_totals["essential"],
                "categories": essential_categories
            },
            "growth_aligned": {
                "total": grouped_totals["growth_aligned"],
                "categories": growth_categories
            },
            "controllable": {
                "total": grouped_totals["controllable"],
                "categories": controllable_categories
            },
            "extraordinary": {
                "total": grouped_totals["extraordinary"],
                "categories": extraordinary_categories
            },
            "uncategorized": {
                "total": grouped_totals["uncategorized"],
                "categories": [
                    item for item in categorized_expenses
                    if item["impact_group"] == "uncategorized"
                ]
            }
        },
        "highest_controllable_category": highest_controllable_category,
        "unusual_months": unusual_months,
        "recurring_categories": recurring_summary[:10],
        "insights": insights,
        "warnings": warnings,
        "opportunities": opportunities
    }