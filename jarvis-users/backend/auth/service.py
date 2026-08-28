import os
import time
from threading import Lock
from typing import Any
from uuid import UUID

import requests
from fastapi import HTTPException, status

from backend.core.database import get_connection


SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
OWNER_SUPABASE_USER_IDS = {
    value.strip().lower()
    for value in os.getenv("OWNER_SUPABASE_USER_IDS", "").split(",")
    if value.strip()
}
AUTH_VERIFY_CACHE_SECONDS = max(15, int(os.getenv("AUTH_VERIFY_CACHE_SECONDS", "300")))

_verified_tokens: dict[str, tuple[float, dict[str, Any]]] = {}
_token_cache_lock = Lock()
_http = requests.Session()


def _serialize_profile(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "supabase_user_id": str(row["supabase_user_id"]),
        "email": row["email"],
        "display_name": row.get("display_name"),
        "role": row["role"],
        "status": row["status"],
        "onboarding_completed": bool(row["onboarding_completed"]),
        "onboarding_level": row.get("onboarding_level"),
        "plan_selected": bool(row.get("plan_selected", False)),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "last_login_at": row.get("last_login_at"),
    }


def verify_supabase_token(access_token: str) -> dict[str, Any]:
    now = time.monotonic()
    with _token_cache_lock:
        cached = _verified_tokens.get(access_token)
        if cached and cached[0] > now:
            return cached[1]
        if cached:
            _verified_tokens.pop(access_token, None)

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="Faltan SUPABASE_URL o SUPABASE_ANON_KEY.")

    try:
        response = _http.get(
            f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="No se pudo validar la sesión con Supabase.") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de Supabase inválido o expirado.")

    payload = response.json()
    email = str(payload.get("email") or "").strip().lower()
    raw_id = payload.get("id")
    if not email or not raw_id:
        raise HTTPException(status_code=401, detail="Supabase no devolvió email o id de usuario.")
    try:
        supabase_user_id = str(UUID(str(raw_id)))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Supabase devolvió un id inválido.") from exc

    metadata = payload.get("user_metadata") or {}
    verified = {
        "supabase_user_id": supabase_user_id,
        "email": email,
        "display_name": metadata.get("full_name") or metadata.get("display_name") or metadata.get("name"),
    }
    with _token_cache_lock:
        _verified_tokens[access_token] = (now + AUTH_VERIFY_CACHE_SECONDS, verified)
        if len(_verified_tokens) > 256:
            expired = [token for token, item in _verified_tokens.items() if item[0] <= now]
            for token in expired:
                _verified_tokens.pop(token, None)
    return verified


def get_or_create_profile(supabase_user: dict[str, Any]):
    supabase_user_id = supabase_user["supabase_user_id"]
    owner = supabase_user_id.lower() in OWNER_SUPABASE_USER_IDS

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, role FROM profiles WHERE supabase_user_id=%s",
            (supabase_user_id,),
        ).fetchone()
        if existing:
            role = "owner" if owner else existing["role"]
            profile_id = existing["id"]
            conn.execute(
                """UPDATE profiles SET email=%s, display_name=COALESCE(%s, display_name), role=%s,
                          updated_at=NOW(), last_login_at=NOW() WHERE id=%s""",
                (supabase_user["email"], supabase_user.get("display_name"), role, profile_id),
            )
        else:
            row = conn.execute(
                """INSERT INTO profiles (supabase_user_id, email, display_name, role, status, onboarding_completed,
                                          created_at, updated_at, last_login_at)
                   VALUES (%s,%s,%s,%s,'active',FALSE,NOW(),NOW(),NOW()) RETURNING id""",
                (supabase_user_id, supabase_user["email"], supabase_user.get("display_name"), "owner" if owner else "user"),
            ).fetchone()
            profile_id = row["id"]

        conn.commit()

        profile_row = conn.execute(
            """SELECT id, supabase_user_id, email, display_name, role, status,
                      onboarding_completed, onboarding_level, plan_selected, created_at, updated_at, last_login_at
               FROM profiles WHERE id=%s""",
            (profile_id,),
        ).fetchone()
        subscription = conn.execute(
            """SELECT s.id, p.code AS plan, s.status, s.started_at, s.expires_at, s.last_payment_at
               FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.user_id=%s""",
            (profile_id,),
        ).fetchone()

    profile = _serialize_profile(profile_row)
    if profile:
        profile["subscription"] = subscription
    return profile


def authenticate_access_token(access_token: str) -> dict[str, Any]:
    profile = get_or_create_profile(verify_supabase_token(access_token))
    if not profile:
        raise HTTPException(status_code=500, detail="No se pudo crear el perfil del usuario.")
    if profile["status"] != "active":
        raise HTTPException(status_code=403, detail="Tu usuario está bloqueado.")
    return profile
