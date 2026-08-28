from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from backend.ai.gemini_client import ask_gemini
from backend.ai.preferences import get_sports_preferences, update_sports_preferences
from backend.integrations.internet_search import internet_search

CR_TZ = ZoneInfo("America/Costa_Rica")

DEFAULT_OWNER_SPORTS = {
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
        "competitions": [
            "UEFA Champions League", "Mundial de Clubes", "Mundial de selecciones",
        ],
        "timezone": "America/Costa_Rica",
    },
    "notification_style": "Señor",
}


def ensure_owner_sports_preferences() -> dict[str, Any]:
    current = get_sports_preferences() or {}
    merged = {
        **DEFAULT_OWNER_SPORTS,
        **current,
        "f1": {**DEFAULT_OWNER_SPORTS["f1"], **(current.get("f1") or {})},
        "ufc": {**DEFAULT_OWNER_SPORTS["ufc"], **(current.get("ufc") or {})},
        "football": {**DEFAULT_OWNER_SPORTS["football"], **(current.get("football") or {})},
    }
    return update_sports_preferences(merged)


def _normalize_request(scope: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(scope, dict):
        return {
            "scope": str(scope.get("scope") or "all").lower(),
            "query_type": str(scope.get("query_type") or "next").lower(),
            "query": str(scope.get("query") or "").strip(),
        }
    return {"scope": str(scope or "all").lower(), "query_type": "next", "query": ""}


def _build_query(scope: str, query_type: str, user_query: str, prefs: dict[str, Any]) -> str:
    base_suffix = "hora Costa Rica fecha próximo evento confirmado"
    if user_query:
        # Si el usuario preguntó algo concreto, respetamos eso y solo agregamos hora tica.
        return f"{user_query} {base_suffix}"

    if scope in {"f1", "formula1", "formula 1"}:
        if query_type == "radar":
            return "próxima Fórmula 1 sprint clasificación carrera horario Costa Rica"
        return "próxima carrera Fórmula 1 fecha hora Costa Rica"

    if scope == "ufc":
        return "próxima UFC cartelera principal main card fecha hora Costa Rica"

    if scope in {"football", "futbol", "fútbol"}:
        football = prefs.get("football") or {}
        teams = ", ".join(football.get("teams") or DEFAULT_OWNER_SPORTS["football"]["teams"])
        competitions = ", ".join(football.get("competitions") or DEFAULT_OWNER_SPORTS["football"]["competitions"])
        if query_type == "radar":
            return f"próximos partidos {teams} {competitions} fecha hora Costa Rica"
        return f"próximo partido {teams} {competitions} fecha hora Costa Rica"

    return "próximo evento deportivo F1 UFC fútbol fecha hora Costa Rica"


def _concise_sports_answer(scope: str, query_type: str, user_query: str, search_result: dict[str, Any]) -> str:
    if search_result.get("status") != "OK":
        return search_result.get("message", "Señor, no pude consultar el calendario deportivo.")

    results = (search_result.get("results") or [])[:5]
    if not results:
        return "Señor, no encontré un resultado deportivo claro."

    now_cr = datetime.now(CR_TZ).strftime("%Y-%m-%d %H:%M Costa Rica")
    prompt = f"""
Eres J.A.R.V.I.S. Responde SOLO lo que el usuario pidió sobre deportes.
No mandes calendarios completos salvo que el usuario pida "calendario" o "radar".
Usa hora de Costa Rica si aparece o conviértela si el resultado la trae clara.
Si no hay fecha/hora clara, dilo.

Tipo: {scope}
Modo: {query_type}
Pregunta del usuario: {user_query or 'próximo evento'}
Hora actual Costa Rica: {now_cr}
Resultados web:
{json.dumps(results, ensure_ascii=False, indent=2)}

Respuesta máxima:
- Si preguntó por próxima carrera/pelea/partido: 1 a 3 líneas.
- Si pidió calendario/radar: máximo 5 eventos.
- Tono: "Señor,".
"""
    ai = ask_gemini(prompt, route="sports_answer")
    if ai.get("status") == "OK" and (ai.get("text") or "").strip():
        return ai["text"].strip()

    first = results[0]
    return f"Señor, encontré esto: {first.get('title', 'Resultado')}. {first.get('snippet', '')}".strip()


def get_sports_calendar_summary(scope: str | dict[str, Any] = "all") -> dict[str, Any]:
    prefs = ensure_owner_sports_preferences().get("value") or DEFAULT_OWNER_SPORTS
    request = _normalize_request(scope)
    normalized_scope = request["scope"]
    query_type = request["query_type"]
    user_query = request["query"]

    query = _build_query(normalized_scope, query_type, user_query, prefs)
    search_result = internet_search(query)
    message = _concise_sports_answer(normalized_scope, query_type, user_query, search_result)

    return {
        "status": search_result.get("status", "OK"),
        "scope": normalized_scope,
        "query_type": query_type,
        "timezone": "America/Costa_Rica",
        "preferences": prefs,
        "query": query,
        "search": search_result,
        "message": message,
    }


def enqueue_owner_sports_digest_notifications() -> dict[str, Any]:
    """Creates one daily sports digest push job for owner/admin users.

    This is intentionally conservative: it schedules a single concise digest per day,
    instead of spamming one notification per uncertain web result.
    """
    from datetime import time, timedelta, timezone
    from backend.core.database import get_connection
    from backend.notifications.service import ensure_notification_tables

    now_cr = datetime.now(CR_TZ)
    day_key = now_cr.strftime("%Y-%m-%d")
    scheduled_cr = datetime.combine(now_cr.date(), time(7, 0), tzinfo=CR_TZ)
    if scheduled_cr < now_cr:
        scheduled_cr = now_cr + timedelta(minutes=2)
    scheduled_utc = scheduled_cr.astimezone(timezone.utc)

    with get_connection() as conn:
        ensure_notification_tables(conn)
        owners = conn.execute(
            """
            SELECT id
            FROM profiles
            WHERE role IN ('owner', 'admin') AND status = 'active'
            """
        ).fetchall()

        created = 0
        skipped = 0
        # Fast dedupe before spending a Serper/Gemini request.
        pending_by_user = {}
        for owner in owners:
            dedupe_key = f"sports-digest:{owner['id']}:{day_key}"
            exists = conn.execute(
                """
                SELECT id
                FROM notification_jobs
                WHERE user_id = %s AND dedupe_key = %s
                LIMIT 1
                """,
                (int(owner["id"]), dedupe_key),
            ).fetchone()
            if exists:
                skipped += 1
            else:
                pending_by_user[int(owner["id"])] = dedupe_key

        conn.commit()

    if not pending_by_user:
        return {"status": "OK", "created": 0, "skipped": skipped, "message": "Digest deportivo ya programado hoy."}

    summary = get_sports_calendar_summary({"scope": "all", "query_type": "radar", "query": ""})
    body = summary.get("message") or "Señor, no encontré eventos deportivos claros para hoy."
    body = body.replace("Señor Kenneth", "Señor").replace("Señor gatotico99", "Señor")
    if not body.lower().startswith("señor"):
        body = f"Señor, {body}"
    body = body[:450]

    with get_connection() as conn:
        ensure_notification_tables(conn)
        for user_id, dedupe_key in pending_by_user.items():
            row = conn.execute(
                """
                INSERT INTO notification_jobs (user_id, title, body, category, scheduled_at, reference_type, reference_id, dedupe_key, payload)
                VALUES (%s, 'Radar deportivo', %s, 'sports', %s, 'sports_radar', %s, %s, %s::jsonb)
                ON CONFLICT (user_id, dedupe_key) DO NOTHING
                RETURNING id
                """,
                (user_id, body, scheduled_utc, day_key, dedupe_key, json.dumps(summary, ensure_ascii=False)),
            ).fetchone()
            if row:
                created += 1
        conn.commit()

    return {"status": "OK", "created": created, "skipped": skipped, "scheduled_at": scheduled_utc.isoformat(), "summary": summary}
