from datetime import datetime

from backend.core.database import get_connection
from backend.auth.current_user import get_current_user_id


def add_financial_goal(
    name: str,
    target_amount: float,
    current_amount: float = 0,
    target_date: str | None = None,
    priority: str = "medium"
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO financial_goals (
                name,
                target_amount,
                current_amount,
                target_date,
                priority,
                status,
                user_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'active', ?, datetime('now'))
            """,
            (
                name,
                target_amount,
                current_amount,
                target_date,
                priority,
                user_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "target_date": target_date,
        "priority": priority,
        "status": "active",
        "user_id": user_id
    }


def get_financial_goals():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date,
                   priority, status, created_at, user_id
            FROM financial_goals
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return [format_goal(dict(row)) for row in rows]


def get_financial_goal(goal_id: int):
    user_id = get_current_user_id()

    with get_connection() as conn:
        goal = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date,
                   priority, status, created_at, user_id
            FROM financial_goals
            WHERE id = ?
            AND user_id = ?
            """,
            (goal_id, user_id)
        ).fetchone()

    if not goal:
        return {
            "message": "Meta no encontrada.",
            "status": "ERROR"
        }

    return format_goal(dict(goal))


def update_financial_goal(
    goal_id: int,
    name: str,
    target_amount: float,
    current_amount: float,
    target_date: str | None,
    priority: str,
    status: str
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        goal = conn.execute(
            """
            SELECT id
            FROM financial_goals
            WHERE id = ?
            AND user_id = ?
            """,
            (goal_id, user_id)
        ).fetchone()

        if not goal:
            return {
                "message": "Meta no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            UPDATE financial_goals
            SET name = ?,
                target_amount = ?,
                current_amount = ?,
                target_date = ?,
                priority = ?,
                status = ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                name,
                target_amount,
                current_amount,
                target_date,
                priority,
                status,
                goal_id,
                user_id
            )
        )

        conn.commit()

    return get_financial_goal(goal_id)


def delete_financial_goal(goal_id: int):
    user_id = get_current_user_id()

    with get_connection() as conn:
        goal = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date,
                   priority, status, created_at, user_id
            FROM financial_goals
            WHERE id = ?
            AND user_id = ?
            """,
            (goal_id, user_id)
        ).fetchone()

        if not goal:
            return {
                "message": "Meta no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            DELETE FROM financial_goals
            WHERE id = ?
            AND user_id = ?
            """,
            (goal_id, user_id)
        )

        conn.commit()

    return {
        "message": "Meta eliminada correctamente.",
        "deleted_goal": dict(goal),
        "status": "OK"
    }


def add_goal_contribution(goal_id: int, amount: float):
    user_id = get_current_user_id()

    with get_connection() as conn:
        goal = conn.execute(
            """
            SELECT id, current_amount, target_amount
            FROM financial_goals
            WHERE id = ?
            AND user_id = ?
            """,
            (goal_id, user_id)
        ).fetchone()

        if not goal:
            return {
                "message": "Meta no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        new_amount = goal["current_amount"] + amount

        if new_amount >= goal["target_amount"]:
            new_status = "completed"
        else:
            new_status = "active"

        conn.execute(
            """
            UPDATE financial_goals
            SET current_amount = ?,
                status = ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                new_amount,
                new_status,
                goal_id,
                user_id
            )
        )

        conn.commit()

    return get_financial_goal(goal_id)


def format_goal(goal: dict):
    target_amount = goal["target_amount"]
    current_amount = goal["current_amount"]

    remaining_amount = max(target_amount - current_amount, 0)

    progress_percentage = (
        (current_amount / target_amount) * 100
        if target_amount > 0
        else 0
    )

    monthly_required = None
    days_remaining = None

    if goal["target_date"]:
        try:
            today = datetime.now().date()
            target_date = datetime.strptime(goal["target_date"], "%Y-%m-%d").date()
            days_remaining = (target_date - today).days

            if days_remaining > 0:
                months_remaining = days_remaining / 30
                monthly_required = remaining_amount / months_remaining
            else:
                monthly_required = remaining_amount
        except ValueError:
            monthly_required = None
            days_remaining = None

    goal["remaining_amount"] = remaining_amount
    goal["progress_percentage"] = progress_percentage
    goal["days_remaining"] = days_remaining
    goal["monthly_required"] = monthly_required

    return goal


def get_financial_goal_by_name(name: str):
    user_id = get_current_user_id()
    search = f"%{name.lower()}%"

    with get_connection() as conn:
        goal = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date,
                   priority, status, created_at, user_id
            FROM financial_goals
            WHERE lower(name) LIKE ?
            AND status = 'active'
            AND user_id = ?
            LIMIT 1
            """,
            (search, user_id)
        ).fetchone()

    if not goal:
        return {
            "message": f"No encontré una meta activa que coincida con '{name}'.",
            "status": "ERROR"
        }

    return format_goal(dict(goal))