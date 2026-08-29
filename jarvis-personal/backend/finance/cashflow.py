from datetime import datetime, timedelta

from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.service import get_financial_summary


WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def set_pay_schedule(
    pay_frequency: str,
    pay_day: str | None = None,
    first_pay_date: str | None = None,
    notes: str = "",
):
    user_id = get_current_user_id()  # legacy compatibility during migration
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM pay_schedule WHERE workspace_id = %s",
            (workspace_id,),
        )

        cursor = conn.execute(
            """
            INSERT INTO pay_schedule (
                pay_frequency,
                pay_day,
                first_pay_date,
                notes,
                user_id,
                workspace_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (pay_frequency, pay_day, first_pay_date, notes, user_id, workspace_id),
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "pay_frequency": pay_frequency,
        "pay_day": pay_day,
        "first_pay_date": first_pay_date,
        "notes": notes,
        "user_id": user_id,
        "workspace_id": workspace_id,
    }


def get_pay_schedule():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        schedule = conn.execute(
            """
            SELECT id, pay_frequency, pay_day, first_pay_date, notes, user_id, workspace_id, created_at
            FROM pay_schedule
            WHERE workspace_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()

    if not schedule:
        return None

    return dict(schedule)


def get_next_pay_date():
    schedule = get_pay_schedule()

    if not schedule:
        return {
            "status": "ERROR",
            "message": "No existe calendario de pago configurado.",
        }

    today = datetime.now().date()
    pay_frequency = schedule["pay_frequency"]
    pay_day = schedule["pay_day"]

    if pay_frequency == "weekly":
        weekday_number = WEEKDAYS.get(pay_day)

        if weekday_number is None:
            return {
                "status": "ERROR",
                "message": "Día de pago semanal inválido.",
            }

        days_until_pay = (weekday_number - today.weekday()) % 7
        next_pay = today if days_until_pay == 0 else today + timedelta(days=days_until_pay)

        return {
            "status": "OK",
            "pay_frequency": pay_frequency,
            "next_pay_date": str(next_pay),
            "days_until_pay": days_until_pay,
        }

    return {
        "status": "ERROR",
        "message": "Frecuencia de pago todavía no soportada.",
    }


def get_basic_cashflow_forecast():
    summary = get_financial_summary()
    next_pay = get_next_pay_date()

    return {
        "status": "OK",
        "summary": summary,
        "next_pay": next_pay,
        "message": "Forecast básico generado.",
    }
