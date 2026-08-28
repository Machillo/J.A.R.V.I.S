from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection


def add_payment_schedule(
    name: str,
    entity_type: str,
    entity_id: int | None,
    payment_method: str,
    frequency: str,
    day_of_month: int | None = None,
    cut_day: int | None = None,
    payment_day: int | None = None,
    auto_deducted: bool = False,
    notes: str = "",
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO payment_schedules (
                name,
                entity_type,
                entity_id,
                payment_method,
                frequency,
                day_of_month,
                cut_day,
                payment_day,
                auto_deducted,
                notes,
                user_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                name,
                entity_type,
                entity_id,
                payment_method,
                frequency,
                day_of_month,
                cut_day,
                payment_day,
                auto_deducted,
                notes,
                user_id,
            ),
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payment_method": payment_method,
        "frequency": frequency,
        "day_of_month": day_of_month,
        "cut_day": cut_day,
        "payment_day": payment_day,
        "auto_deducted": auto_deducted,
        "notes": notes,
        "user_id": user_id,
    }


def get_payment_schedules():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, entity_type, entity_id, payment_method, frequency,
                   day_of_month, cut_day, payment_day, auto_deducted, notes, user_id, created_at
            FROM payment_schedules
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]
