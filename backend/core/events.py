from backend.core.database import get_connection


def add_event(title: str, event_date: str, event_type: str = "general", description: str = ""):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO events (title, description, event_type, event_date, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (title, description, event_type, event_date)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "title": title,
        "description": description,
        "event_type": event_type,
        "event_date": event_date
    }


def get_events():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, event_type, event_date, created_at
            FROM events
            ORDER BY event_date ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]