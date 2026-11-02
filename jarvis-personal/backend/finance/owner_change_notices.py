"""What changed in the Owner's money, kept until he reads it (preference ``owner_change_notices``).

A notice is written in the same transaction as the command that made the change, never in a read,
and holds only the facts of that moment. What the change means today (where the money goes, what the
automatic savings do) is worked out when it is read (``ai/owner_notices.py``). The Owner only:
callers decide with ``owner_account_context``.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.core.idempotency import mark_applied
from backend.core.time import costa_rica_today

PREFERENCE_KEY = "owner_change_notices"
MAX_NOTICES = 30


def stored(conn, workspace_id: str) -> list[dict[str, Any]]:
    """The workspace's notices, newest first (SELECT only)."""
    row = conn.execute("SELECT preference_value FROM user_preferences WHERE workspace_id=%s AND preference_key=%s",
                       (workspace_id, PREFERENCE_KEY)).fetchone()
    items = (row["preference_value"] or {}).get("items") if row else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _save(conn, workspace_id: str, items: list[dict[str, Any]]) -> None:
    conn.execute(
        """INSERT INTO user_preferences (workspace_id, preference_key, preference_value) VALUES (%s, %s, %s::jsonb)
           ON CONFLICT (workspace_id, preference_key) DO UPDATE SET preference_value = EXCLUDED.preference_value, updated_at = NOW()""",
        (workspace_id, PREFERENCE_KEY, json.dumps({"items": items[:MAX_NOTICES]}, ensure_ascii=False)),
    )


def record(conn, workspace_id: str, facts: dict[str, Any]) -> None:
    """Keep a change (inside the caller's transaction)."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{PREFERENCE_KEY}:{workspace_id}",))
    notice = {"id": uuid.uuid4().hex, "created_on": costa_rica_today().isoformat(), "read": False, **facts}
    _save(conn, workspace_id, [notice, *stored(conn, workspace_id)])


def mark_read(notice_id: str) -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{PREFERENCE_KEY}:{workspace_id}",))
        items = stored(conn, workspace_id)
        if not any(item.get("id") == notice_id for item in items):
            raise HTTPException(status_code=404, detail=tx("Aviso no encontrado.", "Notice not found."))
        _save(conn, workspace_id, [{**item, "read": True} if item.get("id") == notice_id else item for item in items])
        mark_applied(conn)
        conn.commit()
    return {"status": "OK", "id": notice_id}
