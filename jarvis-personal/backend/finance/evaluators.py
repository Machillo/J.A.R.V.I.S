from backend.finance.service import get_financial_summary


PURPOSE_SCORES = {
    "travel": 3,
    "education": 5,
    "debt_consolidation": 5,
    "emergency": 5,
    "investment": 4,
    "vehicle": 3,
    "flight_tickets": 4,
    "luxury": 1,
    "entertainment": 1,
    "general": 2
}


def get_purpose_score(purpose: str):
    normalized_purpose = purpose.lower().strip()

    return PURPOSE_SCORES.get(normalized_purpose, PURPOSE_SCORES["general"])


def evaluate_loan(
    amount: float,
    monthly_payment: float,
    purpose: str = "general"
):
    summary = get_financial_summary()

    available_cash = summary["results"]["available_cash"]
    current_debt_payments = summary["debts"]["monthly_debt_payments"]
    purpose_score = get_purpose_score(purpose)

    new_available_cash = available_cash - monthly_payment
    new_debt_payment_total = current_debt_payments + monthly_payment

    if new_available_cash < 0:
        status = "RED"
        message = (
            f"No recomendado. Una nueva cuota de ₡{monthly_payment:,.2f} "
            f"dejaría tu disponible en ₡{new_available_cash:,.2f}."
        )
    elif new_available_cash < available_cash * 0.25:
        status = "YELLOW"
        message = (
            f"Riesgoso. Podrías pagarlo, pero tu disponible bajaría a "
            f"₡{new_available_cash:,.2f}."
        )
    else:
        status = "GREEN"
        message = (
            f"La cuota es viable. Tu disponible quedaría en "
            f"₡{new_available_cash:,.2f}."
        )

    return {
        "type": "loan_evaluation",
        "requested_amount": amount,
        "monthly_payment": monthly_payment,
        "purpose": purpose,
        "purpose_score": purpose_score,
        "current_available_cash": available_cash,
        "new_available_cash": new_available_cash,
        "current_monthly_debt_payments": current_debt_payments,
        "new_monthly_debt_payments": new_debt_payment_total,
        "status": status,
        "message": message
    }


def evaluate_installment_purchase(
    amount: float,
    month_options: list[int],
    purpose: str = "general"
):
    summary = get_financial_summary()

    available_cash = summary["results"]["available_cash"]
    purpose_score = get_purpose_score(purpose)

    options = []

    for months in month_options:
        monthly_payment = amount / months
        remaining_cash = available_cash - monthly_payment

        if remaining_cash < 0:
            status = "RED"
            message = "No viable con tu disponible actual."
        elif remaining_cash < available_cash * 0.25:
            status = "YELLOW"
            message = "Viable, pero te deja muy ajustado."
        else:
            status = "GREEN"
            message = "Viable según tu disponible actual."

        options.append({
            "months": months,
            "monthly_payment": monthly_payment,
            "remaining_cash": remaining_cash,
            "status": status,
            "message": message
        })

    viable_options = [
        option for option in options
        if option["status"] in ["GREEN", "YELLOW"]
    ]

    if not viable_options:
        recommended_option = None
        final_message = "Ninguna opción es recomendable con tu disponible actual."
    else:
        green_options = [
            option for option in viable_options
            if option["status"] == "GREEN"
        ]

        if green_options:
            recommended_option = min(green_options, key=lambda option: option["months"])
        else:
            recommended_option = max(viable_options, key=lambda option: option["months"])

        final_message = (
            f"La mejor opción parece ser {recommended_option['months']} meses, "
            f"con una cuota aproximada de ₡{recommended_option['monthly_payment']:,.2f}."
        )

    return {
        "type": "installment_purchase_evaluation",
        "purchase_amount": amount,
        "purpose": purpose,
        "purpose_score": purpose_score,
        "available_cash": available_cash,
        "options": options,
        "recommended_option": recommended_option,
        "message": final_message
    }