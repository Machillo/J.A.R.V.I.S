from backend.finance.service import get_financial_summary
from backend.finance.strategies import (
    get_debt_avalanche_strategy,
    get_cashflow_strategy,
    get_saving_strategy,
    get_investment_strategy,
    get_all_strategies,
)


def select_recommended_strategy():
    summary = get_financial_summary()

    debt_total = summary["debts"]["debt_total"]
    monthly_debt_payments = summary["debts"]["monthly_debt_payments"]
    available_cash = summary["results"]["available_cash"]
    savings_total = summary["assets"]["savings_total"]
    fixed_expenses_total = summary["expenses"]["fixed_expenses_total"]
    total_income = summary["income"]["total_income"]

    if (
        total_income == 0
        and debt_total == 0
        and available_cash == 0
        and savings_total == 0
        and fixed_expenses_total == 0
    ):
        return {
            "recommended_strategy": "missing_data",
            "name": "Datos financieros incompletos",
            "reason": "No hay información financiera suficiente para recomendar una estrategia.",
            "summary": summary,
            "action_plan": [
                "Configurar perfil laboral.",
                "Registrar deducciones.",
                "Registrar deudas.",
                "Registrar gastos fijos.",
                "Registrar ahorros o inversiones si existen."
            ]
        }

    if available_cash < 0:
        return {
            "recommended_strategy": "stabilize_cashflow",
            "name": "Estabilizar flujo",
            "reason": "Tus gastos y cuotas superan tu ingreso disponible. La prioridad es reducir obligaciones o gastos fijos.",
            "summary": summary,
            "action_plan": [
                "No asumir nuevas deudas.",
                "Revisar gastos fijos.",
                "Evitar compras no esenciales.",
                "Buscar liberar cuota mensual."
            ]
        }

    if debt_total > 0 and monthly_debt_payments > available_cash:
        return {
            "recommended_strategy": "cashflow",
            "name": "Flujo de caja",
            "reason": "Las cuotas de deuda consumen demasiado de tu dinero libre. Conviene priorizar liberar cuota mensual.",
            "strategy": get_cashflow_strategy(),
            "summary": summary
        }

    if debt_total > 0:
        return {
            "recommended_strategy": "debt_avalanche",
            "name": "Avalancha",
            "reason": "Tienes deudas activas. Matemáticamente conviene priorizar la deuda con mayor interés.",
            "strategy": get_debt_avalanche_strategy(),
            "summary": summary
        }

    if savings_total < fixed_expenses_total:
        return {
            "recommended_strategy": "emergency_fund",
            "name": "Fondo de emergencia",
            "reason": "No hay deudas activas, pero tu fondo de emergencia aún es bajo.",
            "strategy": get_saving_strategy(),
            "summary": summary
        }

    return {
        "recommended_strategy": "investment",
        "name": "Inversión",
        "reason": "Tu situación permite empezar a priorizar inversión.",
        "strategy": get_investment_strategy(),
        "summary": summary
    }


def get_strategy_report():
    return {
        "recommended": select_recommended_strategy(),
        "library": get_all_strategies()
    }