"""Personal appearance preferences (theme, palette, accent, text size, typeface, density, surfaces).

Neutral by design: the values are the closed option ids of
`jarvis-personal/native/design-tokens/appearance.json` (test_appearance_catalog.py keeps both in
step), they hold no financial data, and they are read and written only for the calling account
inside its own workspace. Who may use them is decided by the routes (phase 1: the verified Owner
only, appearance_routes.py); nothing here depends on who the Owner is.

Storage is the existing `user_preferences` key/value table (unique per workspace and key), with
one key per account so two members of a shared workspace never share an appearance. No row, or an
empty value, means "the defaults": a GET never writes, and an unreadable stored value falls back to
the defaults field by field instead of failing the app. A reset writes the empty value instead of
deleting the row: the application role has SELECT, INSERT and UPDATE on this table, not DELETE.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection

APPEARANCE_VERSION = 1

Theme = Literal["system", "light", "dark"]
Palette = Literal["oceano", "clasico", "arena", "grafito"]
Accent = Literal["cian", "teal", "ciruela", "tinta"]
TextSize = Literal["s", "m", "l", "xl"]
Typeface = Literal["system", "editorial"]
Density = Literal["comfortable", "compact"]
Surfaces = Literal["outlined", "tonal"]


class AppearancePreferences(BaseModel):
    """A complete appearance: every field is required and must be one of the catalog's ids."""

    model_config = ConfigDict(extra="forbid")

    theme: Theme
    palette: Palette
    accent: Accent
    text_size: TextSize
    typeface: Typeface
    density: Density
    surfaces: Surfaces


DEFAULTS = AppearancePreferences(
    theme="system", palette="oceano", accent="cian", text_size="m", typeface="system", density="comfortable", surfaces="outlined",
)


def _key(account_id: str) -> str:
    return f"appearance.v{APPEARANCE_VERSION}.account.{account_id}"


def _with_defaults(stored: Any) -> AppearancePreferences:
    """The stored value field by field; anything missing or no longer valid is the default."""
    values = DEFAULTS.model_dump()
    if isinstance(stored, dict):
        for field in values:
            candidate = {**values, field: stored.get(field)}
            try:
                values[field] = AppearancePreferences(**candidate).model_dump()[field]
            except ValueError:
                continue
    return AppearancePreferences(**values)


def _payload(preferences: AppearancePreferences, stored: bool, updated_at: Any) -> dict:
    return {
        "version": APPEARANCE_VERSION,
        "preferences": preferences.model_dump(),
        "defaults": DEFAULTS.model_dump(),
        "stored": stored,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
    }


def get_appearance() -> dict:
    workspace_id, account_id = get_current_workspace_id(), get_current_account_id()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT preference_value, updated_at
            FROM user_preferences
            WHERE workspace_id = %s AND preference_key = %s
            """,
            (workspace_id, _key(account_id)),
        ).fetchone()
    value = row["preference_value"] if row else None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = None
    if not value:
        return _payload(DEFAULTS, stored=False, updated_at=None)
    return _payload(_with_defaults(value), stored=True, updated_at=row.get("updated_at"))


def _write(value: dict):
    workspace_id, account_id = get_current_workspace_id(), get_current_account_id()
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO user_preferences (workspace_id, preference_key, preference_value)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (workspace_id, preference_key)
            DO UPDATE SET preference_value = EXCLUDED.preference_value, updated_at = NOW()
            RETURNING updated_at
            """,
            (workspace_id, _key(account_id), json.dumps(value)),
        ).fetchone()
        conn.commit()
    return (row or {}).get("updated_at")


def save_appearance(preferences: AppearancePreferences) -> dict:
    return _payload(preferences, stored=True, updated_at=_write(preferences.model_dump()))


def reset_appearance() -> dict:
    """Back to the defaults: the stored choice is cleared (an empty value), so future default changes apply."""
    _write({})
    return _payload(DEFAULTS, stored=False, updated_at=None)
