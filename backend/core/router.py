import re

from backend.core.time import get_time
from backend.core.user import get_user
from backend.core.config import get_config
from backend.core.events import get_events
from backend.core.logs import get_logs
from backend.finance.service import get_financial_summary, check_spending, get_debt_by_name
from backend.finance.strategy_rules import select_recommended_strategy


def extract_amount_from_text(text: str):
    numbers = re.findall(r"\d+(?:[.,]\d+)?", text)

    if not numbers:
        return 0

    raw_number = numbers[0].replace(",", ".")
    return float(raw_number)

def extract_debt_name_from_text(text: str):
    text = text.lower()

    known_debts = ["popular", "bac", "reloj", "minicuotas"]

    for debt_name in known_debts:
        if debt_name in text:
            return debt_name

    return ""


def route(intent: str, text: str = ""):
    if intent == "GET_TIME":
        return get_time()

    if intent == "GET_USER":
        return get_user()

    if intent == "GET_CONFIG":
        return get_config()

    if intent == "GET_EVENTS":
        return get_events()

    if intent == "GET_LOGS":
        return get_logs()

    if intent == "GET_FINANCIAL_SUMMARY":
        return get_financial_summary()
    
    if intent == "GET_DEBT_BY_NAME":
        debt_name = extract_debt_name_from_text(text)
        return get_debt_by_name(debt_name)

    if intent == "GET_TOTAL_DEBT":
        summary = get_financial_summary()
        debt_total = summary["debts"]["debt_total"]

        return {
            "message": f"Actualmente debes ₡{debt_total:,.2f}.",
            "debt_total": debt_total
        }

    if intent == "GET_AVAILABLE_CASH":
        summary = get_financial_summary()
        available_cash = summary["results"]["available_cash"]

        return {
            "message": f"Actualmente tienes ₡{available_cash:,.2f} disponibles según los datos registrados.",
            "available_cash": available_cash
        }

    if intent == "CHECK_SPENDING":
        amount = extract_amount_from_text(text)
        return check_spending(amount)
    
    if intent == "GET_RECOMMENDED_STRATEGY":
        return select_recommended_strategy()

    return {
        "message": "No entiendo la intención todavía."
    }