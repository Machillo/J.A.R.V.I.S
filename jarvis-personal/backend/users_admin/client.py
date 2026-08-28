import os

import requests
from fastapi import HTTPException


USERS_API_URL = os.getenv("JARVIS_USERS_API_URL", "http://127.0.0.1:8001").rstrip("/")
ADMIN_API_KEY = os.getenv("JARVIS_ADMIN_API_KEY", "").strip()
_http = requests.Session()


def _headers():
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="JARVIS_ADMIN_API_KEY no está configurada en JARVIS Personal.")
    return {"X-JARVIS-ADMIN-KEY": ADMIN_API_KEY}


def _request(method: str, path: str, **kwargs):
    try:
        response = _http.request(method, f"{USERS_API_URL}{path}", headers=_headers(), timeout=8, **kwargs)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="JARVIS Users no está disponible.") from exc

    payload = response.json() if response.content else {}
    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=payload.get("detail", "Error en JARVIS Users."))
    return payload


def list_users(search: str | None = None):
    params = {"search": search} if search else None
    return _request("GET", "/admin/users", params=params)


def get_user(user_id: int):
    return _request("GET", f"/admin/users/{user_id}")


def update_user_access(user_id: int, payload: dict):
    return _request("PATCH", f"/admin/users/{user_id}/access", json=payload)


def link_owner_personal_identity(personal_supabase_user_id: str):
    return _request("POST", "/admin/owner-link", json={"personal_supabase_user_id": personal_supabase_user_id})
