from __future__ import annotations

import os
from urllib.parse import quote_plus

import requests
from fastapi import HTTPException, status

from backend.auth.current_user import get_current_user
from backend.ai.usage_tracker import assert_can_use_ai, estimate_tokens, record_ai_usage

OWNER_WEB_ACCESS_ONLY = os.getenv("OWNER_WEB_ACCESS_ONLY", "true").lower() == "true"


def _require_web_access():
    user = get_current_user()
    if OWNER_WEB_ACCESS_ONLY and user.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El acceso a internet está reservado para el usuario owner.",
        )
    return user


def should_use_internet(message: str) -> bool:
    text = (message or "").lower()
    triggers = [
        "busca en internet",
        "buscar en internet",
        "búscalo en internet",
        "buscalo en internet",
        "investiga en internet",
        "revisa en internet",
        "consulta internet",
        "con acceso a internet",
        "usa internet",
        "googlea",
    ]
    return any(trigger in text for trigger in triggers)


def internet_search(query: str) -> dict:
    _require_web_access()
    clean_query = (query or "").strip()
    for phrase in [
        "busca en internet",
        "buscar en internet",
        "búscalo en internet",
        "buscalo en internet",
        "investiga en internet",
        "revisa en internet",
        "consulta internet",
        "con acceso a internet",
        "usa internet",
        "googlea",
        "jarvis",
    ]:
        clean_query = clean_query.replace(phrase, "")
    clean_query = clean_query.strip(" :,-") or query

    estimated = estimate_tokens(clean_query) + 200
    assert_can_use_ai(estimated)

    results = []
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": clean_query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()

        abstract = payload.get("AbstractText")
        abstract_url = payload.get("AbstractURL")
        if abstract:
            results.append({"title": payload.get("Heading") or clean_query, "snippet": abstract, "url": abstract_url})

        for topic in payload.get("RelatedTopics", [])[:8]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "").split(" - ")[0][:90],
                    "snippet": topic.get("Text"),
                    "url": topic.get("FirstURL"),
                })
    except Exception as exc:
        return {
            "status": "ERROR",
            "message": f"Señor, no pude consultar internet en este momento: {exc}",
            "query": clean_query,
            "results": [],
        }

    if not results:
        return {
            "status": "OK",
            "message": "Señor, busqué en internet, pero no encontré resultados claros con esa consulta.",
            "query": clean_query,
            "results": [],
        }

    usage = record_ai_usage(clean_query, "\n".join(item.get("snippet", "") for item in results[:3]), route="internet_search", model="duckduckgo_instant_answer")
    bullets = "\n".join(f"- {item['snippet']}" for item in results[:3])

    return {
        "status": "OK",
        "message": f"Señor, encontré esto en internet:\n{bullets}",
        "query": clean_query,
        "results": results[:5],
        "usage": usage,
    }
