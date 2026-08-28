from backend.core.database import get_connection


def get_user():
    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT id, name, country, timezone, created_at
            FROM users
            LIMIT 1
            """
        ).fetchone()

    if not user:
        return None

    return dict(user)