from backend.core.database import get_connection


def add_log(action: str, detail: str = ""):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO logs (action, detail, created_at)
            VALUES (%s, %s, NOW())
            """,
            (action, detail)
        )
        conn.commit()


def get_logs():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, action, detail, created_at
            FROM logs
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]