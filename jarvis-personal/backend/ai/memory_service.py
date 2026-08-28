from __future__ import annotations

import json
import re
from typing import Any

from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection

MEMORY_CATEGORIES = {
    "personal": "Datos personales",
    "sports": "Deportes",
    "voice": "Voz",
    "style": "Estilo",
    "finance": "Finanzas",
    "preference": "Preferencias",
    "project": "Proyecto",
    "other": "General",
}

DEFAULT_PROFILE_PREFERENCES = {
    "response_style": "breve, directo y útil",
    "notification_style": "Señor",
    "voice_gender": "male",
    "voice_speed": "slow",
    "voice_tone": "serio, humano y elegante",
}


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _infer_category(text: str, requested_category: str | None = None) -> str:
    if requested_category in MEMORY_CATEGORIES:
        return requested_category

    normalized = text.lower()
    if any(word in normalized for word in ["f1", "formula", "fórmula", "ufc", "futbol", "fútbol", "equipo", "champions", "mundial"]):
        return "sports"
    if any(word in normalized for word in ["voz", "habla", "leer", "velocidad", "masculina", "masculino", "tono"]):
        return "voice"
    if any(word in normalized for word in ["responde", "respuesta", "estilo", "formal", "corto", "largo"]):
        return "style"
    if any(word in normalized for word in ["deuda", "salario", "gasto", "ahorro", "inversion", "inversión", "bac", "multimoney", "popular"]):
        return "finance"
    if any(word in normalized for word in ["prefiero", "me gusta", "quiero", "odio", "no quiero"]):
        return "preference"
    if any(word in normalized for word in ["jarvis", "proyecto", "frontend", "backend", "supabase", "render", "vercel"]):
        return "project"
    return "other"


def _extract_memory_text(user_message: str) -> str:
    text = _clean_text(user_message)
    lowered = text.lower()
    triggers = [
        "recuerda que",
        "recorda que",
        "recordá que",
        "acuérdate que",
        "acuerdate que",
        "guarda en memoria que",
        "agrega a memoria que",
        "memoriza que",
        "nota que",
    ]
    for trigger in triggers:
        index = lowered.find(trigger)
        if index >= 0:
            return _clean_text(text[index + len(trigger):])
    return text


def ensure_memory_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_items (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
            category TEXT NOT NULL DEFAULT 'other',
            title TEXT,
            content TEXT NOT NULL,
            importance INTEGER NOT NULL DEFAULT 3,
            source TEXT NOT NULL DEFAULT 'manual',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_items_user_active
        ON memory_items(user_id, is_active)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_items_category
        ON memory_items(category)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
            preference_key TEXT NOT NULL,
            preference_value JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, preference_key)
        )
        """
    )


def list_memory_items(category: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    user_id = get_current_user_id()
    limit = max(1, min(int(limit or 100), 250))

    with get_connection() as conn:
        ensure_memory_tables(conn)
        if category:
            rows = conn.execute(
                """
                SELECT id, category, title, content, importance, source, metadata, created_at, updated_at
                FROM memory_items
                WHERE user_id = %s AND is_active = TRUE AND category = %s
                ORDER BY importance DESC, updated_at DESC, id DESC
                LIMIT %s
                """,
                (user_id, category, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, category, title, content, importance, source, metadata, created_at, updated_at
                FROM memory_items
                WHERE user_id = %s AND is_active = TRUE
                ORDER BY importance DESC, updated_at DESC, id DESC
                LIMIT %s
                """,
                (user_id, limit),
            ).fetchall()
        conn.commit()

    return [dict(row) for row in rows]


def search_memory_items(query: str, limit: int = 10) -> list[dict[str, Any]]:
    user_id = get_current_user_id()
    query = _clean_text(query)
    limit = max(1, min(int(limit or 10), 50))

    if not query:
        return list_memory_items(limit=limit)

    terms = [term for term in re.split(r"\W+", query.lower()) if len(term) >= 3]
    like_query = f"%{query.lower()}%"

    with get_connection() as conn:
        ensure_memory_tables(conn)
        rows = conn.execute(
            """
            SELECT id, category, title, content, importance, source, metadata, created_at, updated_at
            FROM memory_items
            WHERE user_id = %s
              AND is_active = TRUE
              AND (
                LOWER(content) LIKE %s
                OR LOWER(COALESCE(title, '')) LIKE %s
                OR LOWER(category) LIKE %s
              )
            ORDER BY importance DESC, updated_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, like_query, like_query, like_query, limit),
        ).fetchall()
        conn.commit()

    results = [dict(row) for row in rows]
    if results or not terms:
        return results

    # Fallback más flexible: trae memoria y filtra por palabras.
    all_items = list_memory_items(limit=100)
    filtered = []
    for item in all_items:
        haystack = f"{item.get('title') or ''} {item.get('content') or ''} {item.get('category') or ''}".lower()
        if any(term in haystack for term in terms):
            filtered.append(item)
    return filtered[:limit]


def create_memory_item(
    content: str,
    category: str | None = None,
    title: str | None = None,
    importance: int = 3,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_id = get_current_user_id()
    content = _clean_text(content)
    if not content:
        return {"status": "ERROR", "message": "No hay contenido para guardar en memoria."}

    category = _infer_category(content, category)
    importance = max(1, min(int(importance or 3), 5))
    title = _clean_text(title or content[:80])

    with get_connection() as conn:
        ensure_memory_tables(conn)
        existing = conn.execute(
            """
            SELECT id
            FROM memory_items
            WHERE user_id = %s AND is_active = TRUE AND LOWER(content) = LOWER(%s)
            LIMIT 1
            """,
            (user_id, content),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE memory_items
                SET category = %s,
                    title = %s,
                    importance = GREATEST(importance, %s),
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (category, title, importance, existing["id"], user_id),
            )
            conn.commit()
            return {
                "status": "OK",
                "message": "Memoria actualizada.",
                "id": existing["id"],
                "category": category,
                "content": content,
            }

        cursor = conn.execute(
            """
            INSERT INTO memory_items (user_id, category, title, content, importance, source, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (user_id, category, title, content, importance, source, _json(metadata)),
        )
        conn.commit()

    return {
        "status": "OK",
        "message": "Memoria guardada.",
        "id": cursor.lastrowid,
        "category": category,
        "content": content,
    }


def remember_from_message(user_message: str) -> dict[str, Any]:
    content = _extract_memory_text(user_message)
    return create_memory_item(content=content, source="chat")


def forget_memory_item(memory_id: int) -> dict[str, Any]:
    user_id = get_current_user_id()
    with get_connection() as conn:
        ensure_memory_tables(conn)
        result = conn.execute(
            """
            UPDATE memory_items
            SET is_active = FALSE, updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (memory_id, user_id),
        )
        conn.commit()
    return {"status": "OK", "message": "Memoria eliminada.", "updated": result.rowcount}


def get_profile_preferences() -> dict[str, Any]:
    user_id = get_current_user_id()
    with get_connection() as conn:
        ensure_memory_tables(conn)
        row = conn.execute(
            """
            SELECT preference_value
            FROM user_preferences
            WHERE user_id = %s AND preference_key = 'profile'
            """,
            (user_id,),
        ).fetchone()
        conn.commit()

    prefs = dict(DEFAULT_PROFILE_PREFERENCES)
    if row and isinstance(row.get("preference_value"), dict):
        prefs.update(row["preference_value"])
    return prefs


def update_profile_preferences(payload: dict[str, Any]) -> dict[str, Any]:
    user_id = get_current_user_id()
    current = get_profile_preferences()
    allowed = set(DEFAULT_PROFILE_PREFERENCES.keys()) | {"display_name", "timezone", "language", "avatar_data_url"}
    clean_payload = {key: value for key, value in (payload or {}).items() if key in allowed}
    merged = {**current, **clean_payload}

    with get_connection() as conn:
        ensure_memory_tables(conn)
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, preference_key, preference_value)
            VALUES (%s, 'profile', %s::jsonb)
            ON CONFLICT (user_id, preference_key)
            DO UPDATE SET preference_value = EXCLUDED.preference_value, updated_at = NOW()
            """,
            (user_id, _json(merged)),
        )
        conn.commit()

    return {"status": "OK", "value": merged}


def get_relevant_memory_context(user_message: str, limit: int = 8) -> dict[str, Any]:
    profile = get_profile_preferences()
    relevant = search_memory_items(user_message, limit=limit)
    important = list_memory_items(limit=6)

    # Combina relevantes + importantes sin duplicar.
    seen = set()
    combined = []
    for item in relevant + important:
        item_id = item.get("id")
        if item_id in seen:
            continue
        seen.add(item_id)
        combined.append(item)
        if len(combined) >= limit:
            break

    return {
        "profile_preferences": profile,
        "memories": combined,
    }


def memory_summary() -> dict[str, Any]:
    items = list_memory_items(limit=250)
    by_category: dict[str, int] = {}
    for item in items:
        by_category[item.get("category") or "other"] = by_category.get(item.get("category") or "other", 0) + 1
    return {
        "status": "OK",
        "total": len(items),
        "categories": by_category,
        "items": items[:50],
        "profile_preferences": get_profile_preferences(),
        "category_labels": MEMORY_CATEGORIES,
    }
