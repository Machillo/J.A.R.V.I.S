from __future__ import annotations

from typing import Any

from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection

DEFAULT_SPORTS_PREFS = {
    "f1": {
        "enabled": True,
        "sessions": ["sprint", "clasificación", "carrera"],
        "timezone": "America/Costa_Rica",
    },
    "ufc": {
        "enabled": True,
        "scope": "main_card",
        "timezone": "America/Costa_Rica",
    },
    "football": {
        "enabled": True,
        "teams": [
            "LDA", "Barcelona", "Manchester City", "Arsenal", "Milan", "Inter",
            "PSG", "Bayern Munich", "Borussia Dortmund", "Costa Rica selección",
        ],
        "competitions": ["UEFA Champions League", "Mundial de Clubes", "Mundial de selecciones"],
        "timezone": "America/Costa_Rica",
    },
    "notification_style": "Señor",
}


def ensure_preference_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            preference_key TEXT NOT NULL,
            preference_value JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, preference_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_subscriptions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'browser',
            endpoint TEXT,
            payload JSONB,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, channel, endpoint)
        )
        """
    )


def get_preference(key: str, default: Any = None) -> Any:
    user_id = get_current_user_id()
    with get_connection() as conn:
        ensure_preference_tables(conn)
        row = conn.execute(
            """
            SELECT preference_value
            FROM user_preferences
            WHERE user_id = %s AND preference_key = %s
            """,
            (user_id, key),
        ).fetchone()
        conn.commit()
    return row["preference_value"] if row else default


def set_preference(key: str, value: Any) -> dict:
    user_id = get_current_user_id()
    with get_connection() as conn:
        ensure_preference_tables(conn)
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, preference_key, preference_value)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (user_id, preference_key)
            DO UPDATE SET preference_value = EXCLUDED.preference_value, updated_at = NOW()
            """,
            (user_id, key, __import__('json').dumps(value, ensure_ascii=False)),
        )
        conn.commit()
    return {"status": "OK", "key": key, "value": value}


def get_sports_preferences() -> dict:
    prefs = get_preference("sports", DEFAULT_SPORTS_PREFS) or DEFAULT_SPORTS_PREFS.copy()
    # Compatibilidad con versiones anteriores donde f1/ufc eran booleanos.
    if isinstance(prefs.get("f1"), bool):
        prefs["f1"] = {**DEFAULT_SPORTS_PREFS["f1"], "enabled": prefs.get("f1")}
    if isinstance(prefs.get("ufc"), bool):
        prefs["ufc"] = {**DEFAULT_SPORTS_PREFS["ufc"], "enabled": prefs.get("ufc")}
    football = prefs.get("football") or {}
    prefs["football"] = {**DEFAULT_SPORTS_PREFS["football"], **football}
    return prefs


def update_sports_preferences(payload: dict) -> dict:
    current = get_sports_preferences() or DEFAULT_SPORTS_PREFS.copy()
    football = current.get("football") or {}
    incoming_football = payload.get("football") or {}
    merged = {
        **current,
        **{k: v for k, v in payload.items() if k != "football"},
        "football": {**football, **incoming_football},
    }
    return set_preference("sports", merged)


def save_browser_subscription(payload: dict) -> dict:
    user_id = get_current_user_id()
    endpoint = payload.get("endpoint") or "local-browser"
    with get_connection() as conn:
        ensure_preference_tables(conn)
        conn.execute(
            """
            INSERT INTO notification_subscriptions (user_id, channel, endpoint, payload, enabled)
            VALUES (%s, 'browser', %s, %s::jsonb, TRUE)
            ON CONFLICT (user_id, channel, endpoint)
            DO UPDATE SET payload = EXCLUDED.payload, enabled = TRUE, updated_at = NOW()
            """,
            (user_id, endpoint, __import__('json').dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    return {"status": "OK", "message": "Notificaciones registradas para este navegador."}
