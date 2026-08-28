import os
from typing import Any
from uuid import UUID

import requests
from fastapi import HTTPException

from backend.core.database import get_connection


PERSONAL_API_URL = os.getenv("JARVIS_PERSONAL_API_URL", "http://127.0.0.1:8000").rstrip("/")
BRIDGE_API_KEY = os.getenv("JARVIS_OWNER_BRIDGE_API_KEY", "").strip()
_http = requests.Session()
CONFIGURED_OWNER_UIDS = {
    value.strip().lower()
    for value in os.getenv("OWNER_SUPABASE_USER_IDS", "").split(",")
    if value.strip()
}


def _normalize_uuid(value: str, *, field: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} no es un UUID válido.") from exc


def get_personal_link(profile_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, users_profile_id, personal_supabase_user_id, personal_allowed_user_id,
                   status, linked_at, verified_at, updated_at
            FROM owner_personal_links
            WHERE users_profile_id=%s
            """,
            (profile_id,),
        ).fetchone()
    if not row:
        return None
    row["personal_supabase_user_id"] = str(row["personal_supabase_user_id"])
    return row


def bridge_status(profile: dict[str, Any]) -> dict[str, Any]:
    if profile.get("role") != "owner":
        return {"eligible": False, "linked": False, "status": "not_owner"}
    link = get_personal_link(int(profile["id"]))
    if not link:
        return {"eligible": True, "linked": False, "status": "not_linked"}
    return {
        "eligible": True,
        "linked": link["status"] == "active",
        "status": link["status"],
        "verified_at": link.get("verified_at"),
    }


def _verify_with_personal(personal_supabase_user_id: str) -> dict[str, Any]:
    if not BRIDGE_API_KEY:
        raise HTTPException(status_code=503, detail="JARVIS_OWNER_BRIDGE_API_KEY no está configurada en JARVIS Users.")
    try:
        response = _http.post(
            f"{PERSONAL_API_URL}/internal/owner-bridge/verify",
            headers={"X-JARVIS-BRIDGE-KEY": BRIDGE_API_KEY},
            json={"personal_supabase_user_id": personal_supabase_user_id},
            timeout=8,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="JARVIS Personal no está disponible para verificar el vínculo.") from exc

    payload = response.json() if response.content else {}
    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=payload.get("detail", "Personal rechazó el vínculo."))
    if not payload.get("verified"):
        raise HTTPException(status_code=403, detail="JARVIS Personal no verificó la identidad owner.")
    return payload


def bind_owner_to_personal(personal_supabase_user_id: str) -> dict[str, Any]:
    personal_uid = _normalize_uuid(personal_supabase_user_id, field="personal_supabase_user_id")
    verification = _verify_with_personal(personal_uid)

    if len(CONFIGURED_OWNER_UIDS) != 1:
        raise HTTPException(
            status_code=409,
            detail="OWNER_SUPABASE_USER_IDS debe contener exactamente el UUID de la cuenta owner pública que querés vincular.",
        )
    configured_owner_uid = next(iter(CONFIGURED_OWNER_UIDS))

    with get_connection() as conn:
        owner = conn.execute(
            """SELECT id, account_id, supabase_user_id, role, status
               FROM profiles WHERE supabase_user_id=%s""",
            (configured_owner_uid,),
        ).fetchone()
        if not owner:
            raise HTTPException(
                status_code=404,
                detail="La cuenta configurada en OWNER_SUPABASE_USER_IDS todavía no inició sesión en JARVIS Users.",
            )
        if owner["role"] != "owner":
            raise HTTPException(status_code=409, detail="La cuenta configurada no tiene rol owner en JARVIS Users.")
        if owner["status"] != "active":
            raise HTTPException(status_code=409, detail="El owner de JARVIS Users no está activo.")

        conn.execute(
            """
            INSERT INTO owner_personal_links (
                users_profile_id, personal_supabase_user_id, personal_allowed_user_id,
                status, linked_at, verified_at, updated_at
            )
            VALUES (%s,%s,%s,'active',NOW(),NOW(),NOW())
            ON CONFLICT (users_profile_id) DO UPDATE SET
                personal_supabase_user_id=EXCLUDED.personal_supabase_user_id,
                personal_allowed_user_id=EXCLUDED.personal_allowed_user_id,
                status='active',
                verified_at=NOW(),
                updated_at=NOW()
            """,
            (owner["id"], personal_uid, verification.get("personal_allowed_user_id")),
        )
        conn.commit()

    return {
        "status": "linked",
        "users_profile_id": owner["id"],
        "users_account_id": str(owner["account_id"]),
        "users_supabase_user_id": str(owner["supabase_user_id"]),
        "personal_supabase_user_id": personal_uid,
        "verified": True,
    }
