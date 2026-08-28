import os
from typing import Any
from uuid import UUID

import requests
from fastapi import HTTPException, status

from backend.core.database import get_connection


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
VALID_ROLES = {"owner", "admin", "user"}
VALID_STATUSES = {"active", "blocked"}
OWNER_SUPABASE_USER_IDS = {
    value.strip().lower()
    for value in os.getenv("OWNER_SUPABASE_USER_IDS", "").split(",")
    if value.strip()
}


def _normalize_email(email: str) -> str:
    return email.lower().strip()


def _serialize_profile(row) -> dict[str, Any] | None:
    if not row:
        return None

    data = dict(row)
    return {
        "id": data.get("id"),
        "supabase_user_id": str(data.get("supabase_user_id")) if data.get("supabase_user_id") else None,
        "email": data.get("email"),
        "display_name": data.get("display_name"),
        "role": data.get("role"),
        "status": data.get("status"),
        "onboarding_completed": bool(data.get("onboarding_completed")),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "last_login_at": data.get("last_login_at"),
    }


def verify_supabase_token(access_token: str) -> dict[str, Any]:
    """Validate the bearer token directly against the JARVIS Users Supabase project."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Faltan SUPABASE_URL o SUPABASE_ANON_KEY para JARVIS Users.",
        )

    response = requests.get(
        f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de Supabase inválido o expirado.",
        )

    payload = response.json()
    email = payload.get("email")
    supabase_user_id = payload.get("id")

    if not email or not supabase_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase no devolvió email o id de usuario.",
        )

    try:
        normalized_uuid = str(UUID(str(supabase_user_id)))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase devolvió un identificador de usuario inválido.",
        ) from exc

    metadata = payload.get("user_metadata") or {}
    return {
        "supabase_user_id": normalized_uuid,
        "email": _normalize_email(email),
        "display_name": metadata.get("full_name") or metadata.get("display_name") or metadata.get("name"),
        "raw": payload,
    }


def get_profiles():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, supabase_user_id, email, display_name, role, status,
                   onboarding_completed, created_at, updated_at, last_login_at
            FROM profiles
            ORDER BY id ASC
            """
        ).fetchall()

    return [_serialize_profile(row) for row in rows]


def get_profile_by_supabase_user_id(supabase_user_id: str):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, supabase_user_id, email, display_name, role, status,
                   onboarding_completed, created_at, updated_at, last_login_at
            FROM profiles
            WHERE supabase_user_id = %s
            """,
            (supabase_user_id,),
        ).fetchone()
    return _serialize_profile(row)


def _is_owner_supabase_id(supabase_user_id: str) -> bool:
    return supabase_user_id.lower() in OWNER_SUPABASE_USER_IDS


def _ensure_basic_subscription(conn, profile_id: int) -> None:
    conn.execute(
        """
        INSERT INTO subscriptions (user_id, plan_id, status, created_at, updated_at)
        SELECT %s, id, 'pending', NOW(), NOW()
        FROM plans
        WHERE code = 'basic'
        ON CONFLICT (user_id) DO NOTHING
        """,
        (profile_id,),
    )


def get_or_create_profile(supabase_user: dict[str, Any]):
    supabase_user_id = supabase_user["supabase_user_id"]
    desired_role = "owner" if _is_owner_supabase_id(supabase_user_id) else "user"

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, supabase_user_id, email, display_name, role, status,
                   onboarding_completed, created_at, updated_at, last_login_at
            FROM profiles
            WHERE supabase_user_id = %s
            """,
            (supabase_user_id,),
        ).fetchone()

        if row:
            profile_id = row["id"]
            role = "owner" if desired_role == "owner" else row["role"]
            conn.execute(
                """
                UPDATE profiles
                SET email = %s,
                    display_name = COALESCE(%s, display_name),
                    role = %s,
                    updated_at = NOW(),
                    last_login_at = NOW()
                WHERE id = %s
                """,
                (supabase_user["email"], supabase_user.get("display_name"), role, profile_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO profiles (
                    supabase_user_id, email, display_name, role, status,
                    onboarding_completed, created_at, updated_at, last_login_at
                )
                VALUES (%s, %s, %s, %s, 'active', FALSE, NOW(), NOW(), NOW())
                """,
                (
                    supabase_user_id,
                    supabase_user["email"],
                    supabase_user.get("display_name"),
                    desired_role,
                ),
            )
            profile_id = cursor.lastrowid

        _ensure_basic_subscription(conn, profile_id)
        conn.commit()

    return get_profile_by_supabase_user_id(supabase_user_id)


def get_subscription_for_user(user_id: int):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT s.id, p.code AS plan, s.status, s.started_at, s.expires_at,
                   s.last_payment_at, s.created_at, s.updated_at
            FROM subscriptions s
            JOIN plans p ON p.id = s.plan_id
            WHERE s.user_id = %s
            """,
            (user_id,),
        ).fetchone()


def set_profile_role(user_id: int, role: str):
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Rol inválido.")

    with get_connection() as conn:
        existing = conn.execute("SELECT id, role FROM profiles WHERE id = %s", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if existing["role"] == "owner" and role != "owner":
            raise HTTPException(status_code=400, detail="El owner no se degrada desde este endpoint.")
        conn.execute("UPDATE profiles SET role = %s, updated_at = NOW() WHERE id = %s", (role, user_id))
        conn.commit()
    return {"status": "OK", "id": user_id, "role": role}


def set_profile_status(user_id: int, profile_status: str):
    if profile_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Estado inválido.")

    with get_connection() as conn:
        existing = conn.execute("SELECT id, role FROM profiles WHERE id = %s", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if existing["role"] == "owner" and profile_status != "active":
            raise HTTPException(status_code=400, detail="El owner no puede bloquearse desde este endpoint.")
        conn.execute("UPDATE profiles SET status = %s, updated_at = NOW() WHERE id = %s", (profile_status, user_id))
        conn.commit()
    return {"status": "OK", "id": user_id, "profile_status": profile_status}


def authenticate_access_token(access_token: str) -> dict[str, Any]:
    supabase_user = verify_supabase_token(access_token)
    profile = get_or_create_profile(supabase_user)

    if not profile:
        raise HTTPException(status_code=500, detail="No se pudo crear el perfil del usuario.")

    if profile["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tu usuario está bloqueado.")

    subscription = get_subscription_for_user(profile["id"])
    return {**profile, "subscription": subscription}
