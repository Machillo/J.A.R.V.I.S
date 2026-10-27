"""The Owner's profile preferences (display name, avatar, response style…) for the legacy web app.

Moved unchanged from the retired memory_service (JARVIS Memoria was removed): one row per workspace
in `user_preferences`, defaults filled in on read.
"""
from __future__ import annotations

import json
from typing import Any

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection

DEFAULT_PROFILE_PREFERENCES = {
    "response_style": "breve, directo y útil",
    "notification_style": "Señor",
    "voice_gender": "male",
    "voice_speed": "slow",
    "voice_tone": "serio, humano y elegante",
}


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def get_profile_preferences() -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT preference_value
            FROM user_preferences
            WHERE workspace_id = %s AND preference_key = 'profile'
            """,
            (workspace_id,),
        ).fetchone()
        conn.commit()

    prefs = dict(DEFAULT_PROFILE_PREFERENCES)
    if row and isinstance(row.get("preference_value"), dict):
        prefs.update(row["preference_value"])
    return prefs


def update_profile_preferences(payload: dict[str, Any]) -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    current = get_profile_preferences()
    allowed = set(DEFAULT_PROFILE_PREFERENCES.keys()) | {"display_name", "timezone", "language", "avatar_data_url"}
    clean_payload = {key: value for key, value in (payload or {}).items() if key in allowed}
    merged = {**current, **clean_payload}

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_preferences (workspace_id, preference_key, preference_value)
            VALUES (%s, 'profile', %s::jsonb)
            ON CONFLICT (workspace_id, preference_key)
            DO UPDATE SET preference_value = EXCLUDED.preference_value, updated_at = NOW()
            """,
            (workspace_id, _json(merged)),
        )
        conn.commit()

    return {"status": "OK", "value": merged}
