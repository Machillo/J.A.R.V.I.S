from datetime import date

from backend.core.database import get_connection


def set_credit_card_settings(
    name: str,
    cut_day: int,
    payment_day: int
):
    with get_connection() as conn:
        conn.execute("DELETE FROM credit_card_settings")

        cursor = conn.execute(
            """
            INSERT INTO credit_card_settings (
                name,
                cut_day,
                payment_day,
                created_at
            )
            VALUES (?, ?, ?, datetime('now'))
            """,
            (
                name,
                cut_day,
                payment_day
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "cut_day": cut_day,
        "payment_day": payment_day
    }


def get_credit_card_settings():
    with get_connection() as conn:
        settings = conn.execute(
            """
            SELECT id, name, cut_day, payment_day, created_at
            FROM credit_card_settings
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if not settings:
        return None

    return dict(settings)


def evaluate_card_purchase_date():
    settings = get_credit_card_settings()

    if not settings:
        return {
            "status": "ERROR",
            "message": "No existe configuración de tarjeta."
        }

    today = date.today()
    current_day = today.day

    cut_day = settings["cut_day"]
    payment_day = settings["payment_day"]

    if current_day <= cut_day:
        cycle = "current_cycle"
        message = (
            f"Hoy es día {current_day}. Esta compra entra en el corte actual "
            f"del día {cut_day} y se pagaría el día {payment_day} del próximo pago."
        )
    else:
        cycle = "next_cycle"
        message = (
            f"Hoy es día {current_day}. Como ya pasó el corte del día {cut_day}, "
            f"esta compra entra al siguiente ciclo y se pagaría en el próximo mes de pago."
        )

    return {
        "status": "OK",
        "card": settings["name"],
        "today": str(today),
        "current_day": current_day,
        "cut_day": cut_day,
        "payment_day": payment_day,
        "cycle": cycle,
        "message": message
    }

from backend.finance.service import get_financial_summary


def evaluate_card_purchase(
    amount: float,
    description: str = ""
):
    cycle_data = evaluate_card_purchase_date()
    summary = get_financial_summary()

    if cycle_data["status"] != "OK":
        return cycle_data

    available_cash = summary["results"]["available_cash"]
    projected_available_cash = available_cash - amount

    if projected_available_cash < 0:
        status = "RED"
        recommendation = "No recomendado. Esta compra dejaría tu disponible proyectado en negativo."
    elif projected_available_cash < available_cash * 0.25:
        status = "YELLOW"
        recommendation = "Viable, pero te dejaría muy ajustado."
    else:
        status = "GREEN"
        recommendation = "Viable según tu disponible proyectado."

    return {
        "status": status,
        "description": description,
        "purchase_amount": amount,
        "card_cycle": cycle_data,
        "current_available_cash": available_cash,
        "projected_available_cash": projected_available_cash,
        "recommendation": recommendation
    }