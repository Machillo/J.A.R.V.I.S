import hmac
import os
from uuid import UUID

from fastapi import Header, HTTPException, status

from backend.core.database import get_connection


BRIDGE_API_KEY = os.getenv("JARVIS_OWNER_BRIDGE_API_KEY", "").strip()


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
            SELECT id, supabase_user_id, role, status
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
        "role": "owner",
    }
