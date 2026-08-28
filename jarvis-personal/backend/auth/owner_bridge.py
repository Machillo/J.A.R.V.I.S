import base64
import hashlib
import hmac
import json
import os
import time
from uuid import UUID

from fastapi import Header, HTTPException, status

from backend.core.database import get_connection


BRIDGE_API_KEY = os.getenv("JARVIS_OWNER_BRIDGE_API_KEY", "").strip()
BRIDGE_TOKEN_TTL_SECONDS = max(300, int(os.getenv("JARVIS_OWNER_BRIDGE_TOKEN_TTL_SECONDS", "43200")))


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def require_owner_bridge_key(x_jarvis_bridge_key: str | None = Header(default=None)) -> None:
    if not BRIDGE_API_KEY:
        raise HTTPException(status_code=503, detail="JARVIS_OWNER_BRIDGE_API_KEY no está configurada en JARVIS Personal.")
    if not x_jarvis_bridge_key or not hmac.compare_digest(x_jarvis_bridge_key, BRIDGE_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial del owner bridge inválida.")


def verify_personal_owner(personal_supabase_user_id: str) -> dict:
    try:
        personal_uid = str(UUID(str(personal_supabase_user_id)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="personal_supabase_user_id no es válido.") from exc

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, supabase_user_id, role, status
            FROM allowed_users
            WHERE supabase_user_id=%s
            """,
            (personal_uid,),
        ).fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="La identidad no existe todavía en JARVIS Personal. Iniciá sesión una vez en Personal con tu cuenta original.",
        )
    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="La identidad Personal no está activa.")
    if row["role"] != "owner":
        raise HTTPException(status_code=403, detail="La identidad Personal no tiene rol owner.")

    return {
        "verified": True,
        "personal_allowed_user_id": row["id"],
        "personal_supabase_user_id": str(row["supabase_user_id"]),
        "email": row.get("email"),
        "role": "owner",
    }


def issue_owner_bridge_session(personal_supabase_user_id: str) -> dict:
    if not BRIDGE_API_KEY:
        raise HTTPException(status_code=503, detail="JARVIS_OWNER_BRIDGE_API_KEY no está configurada en JARVIS Personal.")

    owner = verify_personal_owner(personal_supabase_user_id)
    now = int(time.time())
    payload = {
        "v": 1,
        "aud": "jarvis-personal-owner",
        "sub": str(owner["personal_supabase_user_id"]),
        "allowed_user_id": int(owner["personal_allowed_user_id"]),
        "iat": now,
        "exp": now + BRIDGE_TOKEN_TTL_SECONDS,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64encode(hmac.new(BRIDGE_API_KEY.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
    return {
        "token": f"{encoded}.{signature}",
        "expires_at": payload["exp"],
        "expires_in": BRIDGE_TOKEN_TTL_SECONDS,
    }


def authenticate_owner_bridge_token(token: str) -> dict:
    if not BRIDGE_API_KEY:
        raise HTTPException(status_code=503, detail="Owner bridge no disponible.")
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Sesión owner inválida.") from exc

    expected = _b64encode(hmac.new(BRIDGE_API_KEY.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Sesión owner inválida.")

    try:
        payload = json.loads(_b64decode(encoded))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Sesión owner inválida.") from exc

    if payload.get("aud") != "jarvis-personal-owner" or int(payload.get("exp", 0)) <= int(time.time()):
        raise HTTPException(status_code=401, detail="La sesión owner expiró. Volvé a entrar desde JARVIS.")

    personal_uid = str(payload.get("sub") or "")
    allowed_user_id = int(payload.get("allowed_user_id") or 0)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, supabase_user_id, role, status
            FROM allowed_users
            WHERE id=%s AND supabase_user_id=%s
            """,
            (allowed_user_id, personal_uid),
        ).fetchone()

    if not row or row["status"] != "active" or row["role"] != "owner":
        raise HTTPException(status_code=403, detail="La identidad owner de Personal ya no está autorizada.")

    return {
        "id": row["id"],
        "email": row["email"],
        "role": "owner",
        "status": row["status"],
        "supabase_user_id": str(row["supabase_user_id"]),
        "auth_source": "users_owner_bridge",
    }
