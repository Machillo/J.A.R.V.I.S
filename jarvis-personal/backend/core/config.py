from backend.core.database import get_connection


def get_config():
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()

    return {row["key"]: row["value"] for row in rows}