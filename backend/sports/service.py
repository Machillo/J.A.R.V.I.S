from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

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
    """Deja guardadas las preferencias deportivas base del owner.

    No consume internet. Solo asegura que el sistema conozca qué deportes/equipos seguir.
    """
    current = get_sports_preferences() or {}
    # Mantiene lo que ya exista, pero rellena lo faltante con tu configuración.
    merged = {
        **DEFAULT_OWNER_SPORTS,
        **current,
        "f1": {**DEFAULT_OWNER_SPORTS["f1"], **(current.get("f1") or {})},
        "ufc": {**DEFAULT_OWNER_SPORTS["ufc"], **(current.get("ufc") or {})},
        "football": {**DEFAULT_OWNER_SPORTS["football"], **(current.get("football") or {})},
    }
    return update_sports_preferences(merged)


def _result_lines(title: str, search_result: dict[str, Any]) -> list[str]:
    status = search_result.get("status")
    if status != "OK":
        return [f"{title}: {search_result.get('message', 'No pude consultar esta sección.')}"]

    rows = [f"{title}:"]
    for item in (search_result.get("results") or [])[:3]:
        item_title = item.get("title") or "Resultado"
        snippet = item.get("snippet") or ""
        link = item.get("link") or ""
        rows.append(f"- {item_title}\n  {snippet}\n  {link}".rstrip())
    return rows


def get_sports_calendar_summary(scope: str = "all") -> dict[str, Any]:
    """Busca calendario deportivo actual usando internet real.

    Importante: no hace búsquedas cada vez que el usuario habla normal. Solo corre cuando
    el intent es sports_schedule o cuando el owner pide actualizar/buscar deportes.
    """
    prefs = ensure_owner_sports_preferences().get("value") or DEFAULT_OWNER_SPORTS
    now_cr = datetime.now(CR_TZ).strftime("%Y-%m-%d %H:%M Costa Rica")

    queries: list[tuple[str, str]] = []

    normalized_scope = (scope or "all").lower()

    if normalized_scope in {"all", "f1", "formula1", "formula 1"} and (prefs.get("f1") or {}).get("enabled", True):
        queries.append((
            "F1",
            "calendario Fórmula 1 próximo GP sprint clasificación carrera hora Costa Rica 2026",
        ))

    if normalized_scope in {"all", "ufc"} and (prefs.get("ufc") or {}).get("enabled", True):
        queries.append((
            "UFC",
            "UFC próxima cartelera principal main card hora Costa Rica peleas",
        ))

    if normalized_scope in {"all", "football", "futbol", "fútbol"} and (prefs.get("football") or {}).get("enabled", True):
        football = prefs.get("football") or {}
        teams = ", ".join(football.get("teams") or DEFAULT_OWNER_SPORTS["football"]["teams"])
        competitions = ", ".join(football.get("competitions") or DEFAULT_OWNER_SPORTS["football"]["competitions"])
        queries.append((
            "Fútbol",
            f"próximos partidos hora Costa Rica {teams} {competitions}",
        ))

    sections = []
    raw_results = []
    for label, query in queries[:4]:
        result = internet_search(query)
        raw_results.append({"label": label, "query": query, "result": result})
        sections.extend(_result_lines(label, result))

    if not sections:
        message = "Señor, no hay deportes activos en sus preferencias."
    else:
        message = (
            f"Señor, actualicé su radar deportivo con hora tica como referencia ({now_cr}).\n\n"
            + "\n\n".join(sections)
            + "\n\nCuando activemos Web Push, usaré esta base para enviarle avisos aunque no tenga J.A.R.V.I.S. abierto."
        )

    return {
        "status": "OK",
        "scope": normalized_scope,
        "timezone": "America/Costa_Rica",
        "preferences": prefs,
        "searches": raw_results,
        "message": message,
    }
