import os
from typing import Any

import requests
from fastapi import HTTPException, status

from backend.core.database import get_connection


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

VALID_ROLES = {"owner", "admin", "user", "viewer"}
VALID_STATUSES = {"active", "blocked", "pending"}


def _normalize_email(email: str) -> str:
    return email.lower().strip()


def _serialize_allowed_user(row) -> dict[str, Any] | None:
    if not row:
        return None

    data = dict(row)
    return {
        "id": data.get("id"),
        "email": data.get("email"),
        "role": data.get("role"),
        "status": data.get("status"),
        "supabase_user_id": data.get("supabase_user_id"),
        "created_at": data.get("created_at"),
        "last_login_at": data.get("last_login_at"),
    }


def verify_supabase_token(access_token: str) -> dict[str, Any]:
    """
    Valida el access_token contra Supabase Auth.
    No confiamos en datos enviados por el frontend sin verificarlos.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Faltan SUPABASE_URL o SUPABASE_ANON_KEY en Render.",
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

    return {
        "supabase_user_id": supabase_user_id,
        "email": _normalize_email(email),
        "raw": payload,
    }


def get_allowed_users():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, email, role, status, supabase_user_id, created_at, last_login_at
            FROM allowed_users
            ORDER BY id ASC
            """
        ).fetchall()

    return [_serialize_allowed_user(row) for row in rows]


def get_allowed_user_by_email(email: str):
    normalized_email = _normalize_email(email)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, role, status, supabase_user_id, created_at, last_login_at
            FROM allowed_users
            WHERE email = %s
            """,
            (normalized_email,),
        ).fetchone()

    return _serialize_allowed_user(row)


def create_allowed_user(email: str, role: str = "user", status: str = "active"):
    normalized_email = _normalize_email(email)

    if role not in VALID_ROLES:
        return {
            "status": "ERROR",
            "message": "Rol inválido.",
        }

    if status not in VALID_STATUSES:
        return {
            "status": "ERROR",
            "message": "Estado inválido.",
        }

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM allowed_users
            WHERE email = %s
            """,
            (normalized_email,),
        ).fetchone()

        if existing:
            return {
                "status": "ERROR",
                "message": "Ese correo ya está autorizado.",
            }

        cursor = conn.execute(
            """
            INSERT INTO allowed_users (
                email,
                role,
                status,
                created_at
            )
            VALUES (%s, %s, %s, NOW())
            """,
            (normalized_email, role, status),
        )

        conn.commit()

    return {
        "status": "OK",
        "message": "Usuario autorizado correctamente.",
        "id": cursor.lastrowid,
    }


def delete_allowed_user(user_id: int):
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT *
            FROM allowed_users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()

        if not existing:
            return {
                "status": "ERROR",
                "message": "Usuario no encontrado.",
            }

        if existing["role"] == "owner":
            return {
                "status": "ERROR",
                "message": "No se puede eliminar el owner.",
            }

        conn.execute(
            """
            DELETE FROM allowed_users
            WHERE id = %s
            """,
            (user_id,),
        )

        conn.commit()

    return {
        "status": "OK",
        "message": "Usuario eliminado.",
    }


def check_user_access(email: str):
    user = get_allowed_user_by_email(email)

    if not user:
        return {
            "allowed": False,
            "message": "Correo no autorizado.",
        }

    if user["status"] != "active":
        return {
            "allowed": False,
            "message": "Usuario no activo.",
            "user": user,
        }

    return {
        "allowed": True,
        "message": "Acceso autorizado.",
        "user": user,
    }


def authenticate_access_token(access_token: str) -> dict[str, Any]:
    supabase_user = verify_supabase_token(access_token)
    app_user = get_allowed_user_by_email(supabase_user["email"])

    if not app_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este correo no está autorizado para usar J.A.R.V.I.S.",
        )

    if app_user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu usuario no está activo.",
        )

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE allowed_users
            SET supabase_user_id = %s,
                last_login_at = NOW()
            WHERE id = %s
            """,
            (supabase_user["supabase_user_id"], app_user["id"]),
        )
        conn.commit()

    return {
        "id": app_user["id"],
        "email": app_user["email"],
        "role": app_user["role"],
        "status": app_user["status"],
        "supabase_user_id": supabase_user["supabase_user_id"],
    }
