from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection


def get_config():
    user_id = get_current_user_id()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE user_id = %s",
            (user_id,),
        ).fetchall()

    return {row["key"]: row["value"] for row in rows}
