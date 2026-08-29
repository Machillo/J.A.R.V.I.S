from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection


def add_log(action: str, detail: str = ""):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO logs (action, detail, user_id, workspace_id, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (action, detail, user_id, workspace_id),
        )
        conn.commit()


def get_logs():
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, action, detail, user_id, created_at
            FROM logs
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,),
        ).fetchall()

    return [dict(row) for row in rows]
