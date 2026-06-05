from __future__ import annotations

import os
import requests
from fastapi import HTTPException, status

from backend.auth.current_user import get_current_user


def is_owner() -> bool:
    user = get_current_user()
    return user.get("role") == "owner" or user.get("email") == "gatotico99@gmail.com"


def internet_search(query: str) -> dict:
    """Búsqueda web real, solo owner.

    Soporta SERPER_API_KEY o TAVILY_API_KEY. Si no hay llave, no cae al motor financiero:
    devuelve una instrucción clara para configurar la búsqueda real.
    """
    if not is_owner():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La búsqueda en internet está restringida al usuario owner.",
        )

    query = (query or "").strip()
    if not query:
        return {"status": "NEEDS_QUERY", "message": "Señor, ¿qué desea que busque en internet?"}

    serper_key = os.getenv("SERPER_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")

    if serper_key:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
            json={"q": query, "gl": "cr", "hl": "es"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("organic", [])[:5]:
            results.append({
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet"),
            })
        return {"status": "OK", "provider": "serper", "query": query, "results": results}

    if tavily_key:
        response = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": tavily_key, "query": query, "search_depth": "basic", "max_results": 5},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("results", [])[:5]:
            results.append({
                "title": item.get("title"),
                "link": item.get("url"),
                "snippet": item.get("content"),
            })
        return {"status": "OK", "provider": "tavily", "query": query, "results": results}

    return {
        "status": "CONFIG_REQUIRED",
        "query": query,
        "message": (
            "Señor, ya detecté que esto es una búsqueda de internet, pero falta configurar "
            "SERPER_API_KEY o TAVILY_API_KEY en Render. No usaré el motor financiero para esta pregunta."
        ),
    }
