from __future__ import annotations

from datetime import datetime, timedelta

from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection


def add_event(title: str, event_date: str, event_type: str = "general", description: str = ""):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO events (title, description, event_type, event_date, user_id, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (title, description, event_type, event_date, user_id),
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "title": title,
        "description": description,
        "event_type": event_type,
        "event_date": event_date,
        "user_id": user_id,
    }


def get_events():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, event_type, event_date, user_id, created_at
            FROM events
            WHERE user_id = %s
            ORDER BY event_date ASC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_upcoming_events(days: int = 30):
    user_id = get_current_user_id()
    today = datetime.now().date()
    limit = today + timedelta(days=days)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, event_type, event_date, user_id, created_at
            FROM events
            WHERE user_id = %s
            AND NULLIF(event_date, '')::date BETWEEN %s AND %s
            ORDER BY NULLIF(event_date, '')::date ASC
            """,
            (user_id, today.isoformat(), limit.isoformat()),
        ).fetchall()

    return [dict(row) for row in rows]
