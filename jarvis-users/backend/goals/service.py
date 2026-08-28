from fastapi import HTTPException

from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection


def get_financial_goals():
    user_id = get_current_user_id()
    with get_connection() as conn:
        return conn.execute(
            """SELECT id, name, target_amount, current_amount, target_date, priority, status, created_at, updated_at
               FROM financial_goals WHERE user_id=%s ORDER BY id DESC""",
            (user_id,),
        ).fetchall()


def add_financial_goal(name: str, target_amount: float, current_amount: float = 0, target_date: str | None = None,
                       priority: str = "medium"):
    user_id = get_current_user_id()
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO financial_goals (user_id, name, target_amount, current_amount, target_date, priority)
               VALUES (%s,%s,%s,%s,%s,%s)
               RETURNING id, name, target_amount, current_amount, target_date, priority, status, created_at, updated_at""",
            (user_id, name, target_amount, current_amount, target_date, priority),
        ).fetchone()
        conn.commit()
    return row


def update_financial_goal(goal_id: int, **payload):
    user_id = get_current_user_id()
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE financial_goals SET name=%s, target_amount=%s, current_amount=%s, target_date=%s,
                      priority=%s, status=%s, updated_at=NOW()
               WHERE id=%s AND user_id=%s
               RETURNING id, name, target_amount, current_amount, target_date, priority, status, created_at, updated_at""",
            (payload["name"], payload["target_amount"], payload["current_amount"], payload.get("target_date"),
             payload["priority"], payload["status"], goal_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Meta no encontrada.")
        conn.commit()
    return row


def delete_financial_goal(goal_id: int):
    user_id = get_current_user_id()
    with get_connection() as conn:
        result = conn.execute("DELETE FROM financial_goals WHERE id=%s AND user_id=%s", (goal_id, user_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Meta no encontrada.")
        conn.commit()
    return {"status": "ok"}
