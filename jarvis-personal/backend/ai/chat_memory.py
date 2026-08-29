from __future__ import annotations

import json
from typing import Any

from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection


PENDING_STATUS = "pending"


def _safe_json_loads(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def get_or_create_chat_session() -> int:
    """Devuelve una sesión activa simple por usuario para conversaciones con JARVIS."""
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        session = conn.execute(
            """
            SELECT id
            FROM chat_sessions
            WHERE workspace_id = %s
            AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()

        if session:
            return session["id"]

        cursor = conn.execute(
            """
            INSERT INTO chat_sessions (user_id, workspace_id, status, created_at, updated_at)
            VALUES (%s, %s, 'active', NOW(), NOW())
            """,
            (user_id, workspace_id),
        )
        conn.commit()

    return cursor.lastrowid


def get_pending_action() -> dict[str, Any] | None:
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, session_id, action_type, status, current_field,
                   payload, missing_fields, created_at, updated_at
            FROM chat_pending_actions
            WHERE workspace_id = %s
            AND status = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (workspace_id, PENDING_STATUS),
        ).fetchone()

    if not row:
        return None

    action = dict(row)
    action["payload"] = _safe_json_loads(action.get("payload"), {})
    action["missing_fields"] = _safe_json_loads(action.get("missing_fields"), [])
    return action


def create_pending_action(
    action_type: str,
    payload: dict[str, Any] | None = None,
    missing_fields: list[str] | None = None,
    current_field: str | None = None,
) -> dict[str, Any]:
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    session_id = get_or_create_chat_session()
    payload = payload or {}
    missing_fields = missing_fields or []

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE chat_pending_actions
            SET status = 'cancelled', updated_at = NOW()
            WHERE workspace_id = %s
            AND status = 'pending'
            """,
            (workspace_id,),
        )

        cursor = conn.execute(
            """
            INSERT INTO chat_pending_actions (
                user_id, workspace_id, session_id, action_type, status, current_field,
                payload, missing_fields, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, 'pending', %s, %s::jsonb, %s::jsonb, NOW(), NOW())
            """,
            (
                user_id,
                workspace_id,
                session_id,
                action_type,
                current_field,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(missing_fields, ensure_ascii=False),
            ),
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "user_id": user_id,
        "session_id": session_id,
        "action_type": action_type,
        "status": "pending",
        "current_field": current_field,
        "payload": payload,
        "missing_fields": missing_fields,
    }


def update_pending_action(
    action_id: int,
    payload: dict[str, Any],
    missing_fields: list[str],
    current_field: str | None,
) -> None:
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE chat_pending_actions
            SET payload = %s::jsonb,
                missing_fields = %s::jsonb,
                current_field = %s,
                updated_at = NOW()
            WHERE id = %s
            AND workspace_id = %s
            """,
            (
                json.dumps(payload, ensure_ascii=False),
                json.dumps(missing_fields, ensure_ascii=False),
                current_field,
                action_id,
                workspace_id,
            ),
        )
        conn.commit()


def finish_pending_action(action_id: int, status: str = "completed") -> None:
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE chat_pending_actions
            SET status = %s,
                updated_at = NOW()
            WHERE id = %s
            AND workspace_id = %s
            """,
            (status, action_id, workspace_id),
        )
        conn.commit()
