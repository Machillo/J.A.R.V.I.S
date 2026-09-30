from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection

# The Owner's agenda horizon: the historical "Próximos eventos" card asked for 45 days, and the
# chat's "¿qué tengo?" answers with the same upcoming events.
AGENDA_DAYS = 45
_EVENT_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")


def add_event(title: str, event_date: str, event_type: str = "general", description: str = ""):
    user_id = get_current_user_id()  # legacy compatibility during migration
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO events (
                title, description, event_type, event_date, workspace_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (title, description, event_type, event_date, workspace_id),
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "title": title,
        "description": description,
        "event_type": event_type,
        "event_date": event_date,
        "user_id": user_id,
        "workspace_id": workspace_id,
    }


def get_events():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, event_type, event_date, user_id, workspace_id, created_at
            FROM events
            WHERE workspace_id = %s
            ORDER BY event_date ASC
            """,
            (workspace_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def event_day(value) -> date | None:
    """The day of a stored event_date ("YYYY-MM-DD", optionally followed by the time), or None when
    it is not a real date. A legacy or malformed value is never guessed into another day."""
    text = str(value or "").strip()
    if not _EVENT_DATE_PREFIX.match(text):
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def get_upcoming_events(days: int = 30, today: date | None = None):
    """Events from today to today + days, in chronological order (day, then the stored time).

    The day is checked in Python, not cast in SQL: one impossible stored date (e.g. "2026-02-30")
    used to make the whole query fail. Such rows are skipped; no stored value is changed."""
    workspace_id = get_current_workspace_id()
    start = today or datetime.now().date()
    limit = start + timedelta(days=days)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, event_type, event_date, user_id, workspace_id, created_at
            FROM events
            WHERE workspace_id = %s
              AND NULLIF(TRIM(event_date::text), '') IS NOT NULL
              AND TRIM(event_date::text) ~ '^\\d{4}-\\d{2}-\\d{2}'
            """,
            (workspace_id,),
        ).fetchall()

    upcoming = []
    for row in rows:
        day = event_day(row.get("event_date"))
        if day is not None and start <= day <= limit:
            upcoming.append((day, str(row.get("event_date") or "").strip(), row.get("id") or 0, dict(row)))
    upcoming.sort(key=lambda item: item[:3])
    return [event for *_, event in upcoming]
