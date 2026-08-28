from backend.finance.service import get_debts, get_financial_summary


def get_debt_avalanche_strategy():
    debts = get_debts()

    sorted_debts = sorted(
        debts,
        key=lambda debt: debt["interest_rate"] or 0,
        reverse=True
    )

    return {
        "strategy": "debt_avalanche",
        "name": "Avalancha",
        "description": "Prioriza pagar primero las deudas con mayor tasa de interés.",
        "priority_order": sorted_debts
    }


def get_debt_snowball_strategy():
    debts = get_debts()

    sorted_debts = sorted(
        debts,
        key=lambda debt: debt["remaining_amount"]
    )

    return {
        "strategy": "debt_snowball",
        "name": "Bola de nieve",
        "description": "Prioriza pagar primero las deudas más pequeñas para liberar motivación y flujo.",
        "priority_order": sorted_debts
    }


def get_cashflow_strategy():
    debts = get_debts()

    sorted_debts = sorted(
        debts,
        key=lambda debt: debt["monthly_payment"],
        reverse=True
    )

    return {
        "strategy": "cashflow",
        "name": "Flujo de caja",
        "description": "Prioriza las deudas con cuotas mensuales más altas para liberar dinero mensual.",
        "priority_order": sorted_debts
    }


def get_saving_strategy():
    summary = get_financial_summary()
    available_cash = summary["results"]["available_cash"]

    if available_cash <= 0:
        recommendation = "No hay margen para ahorro. Prioridad: estabilizar flujo mensual."
        suggested_amount = 0
    elif available_cash < 50000:
        recommendation = "Ahorro mínimo defensivo. Conviene guardar una parte pequeña y evitar nuevos compromisos."
        suggested_amount = available_cash * 0.2
    else:
        recommendation = "Hay margen para ahorro. Conviene separar una parte antes de gastar."
        suggested_amount = available_cash * 0.3

    return {
        "strategy": "saving",
        "name": "Ahorro",
        "description": recommendation,
        "available_cash": available_cash,
        "suggested_monthly_saving": suggested_amount
    }


def get_investment_strategy():
    summary = get_financial_summary()

    debt_total = summary["debts"]["debt_total"]
    available_cash = summary["results"]["available_cash"]
    savings_total = summary["assets"]["savings_total"]

    if debt_total > 0:
        profile = "conservative"
        recommendation = "No se recomienda priorizar inversión todavía. Primero estabilizar deudas y flujo."
        suggested_amount = 0
    elif savings_total < available_cash * 3:
        profile = "moderate"
        recommendation = "Antes de invertir fuerte, conviene construir fondo de emergencia."
        suggested_amount = available_cash * 0.1 if available_cash > 0 else 0
    else:
        profile = "aggressive"
        recommendation = "Ya hay mejor base para inversión. Se puede considerar una estrategia más agresiva."
        suggested_amount = available_cash * 0.3 if available_cash > 0 else 0

    return {
        "strategy": "investment",
        "profile": profile,
        "name": "Inversión",
        "description": recommendation,
        "suggested_monthly_investment": suggested_amount
    }


def get_all_strategies():
    return {
        "debt": {
            "avalanche": get_debt_avalanche_strategy(),
            "snowball": get_debt_snowball_strategy(),
            "cashflow": get_cashflow_strategy()
        },
        "saving": get_saving_strategy(),
        "investment": get_investment_strategy()
    }