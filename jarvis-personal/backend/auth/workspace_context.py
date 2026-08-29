from typing import Any

from fastapi import HTTPException, status


def resolve_personal_workspace_context(conn, legacy_allowed_user_id: int) -> dict[str, Any]:
    """
    Resuelve la identidad JARVIS permanente y el workspace Personal por defecto
    desde el id legacy de allowed_users.

    Durante la migración conservamos allowed_users.id como compatibilidad, pero
    toda funcionalidad nueva debe usar account_id/workspace_id de este contexto.
    """
    row = conn.execute(
        """
        SELECT
            a.id AS account_id,
            a.role AS account_role,
            a.status AS account_status,
            w.id AS workspace_id,
            w.name AS workspace_name,
            w.workspace_type,
            w.status AS workspace_status,
            wm.member_role,
            wm.status AS membership_status
        FROM accounts a
        JOIN workspaces w
          ON w.owner_account_id = a.id
         AND w.workspace_type = 'personal'
         AND w.workspace_key = 'personal:' || a.id::TEXT
        JOIN workspace_members wm
          ON wm.workspace_id = w.id
         AND wm.account_id = a.id
        WHERE a.legacy_allowed_user_id = %s
        LIMIT 1
        """,
        (legacy_allowed_user_id,),
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "La cuenta autenticada todavía no tiene identidad/workspace unificado. "
                "Ejecutá las migraciones de workspace antes de continuar."
            ),
        )

    data = dict(row)

    if data.get("account_status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta JARVIS no está activa.",
        )

    if data.get("workspace_status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El workspace Personal no está activo.",
        )

    if data.get("membership_status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La membresía del workspace no está activa.",
        )

    return {
        "account_id": str(data["account_id"]),
        "account_role": data.get("account_role"),
        "workspace_id": str(data["workspace_id"]),
        "workspace_name": data.get("workspace_name"),
        "workspace_type": data.get("workspace_type"),
        "workspace_role": data.get("member_role"),
    }


def sync_account_auth_identity(
    conn,
    *,
    legacy_allowed_user_id: int,
    supabase_user_id: str,
    effective_role: str,
) -> None:
    """Mantiene accounts sincronizada mientras allowed_users sigue en compatibilidad."""
    conn.execute(
        """
        UPDATE accounts
        SET supabase_user_id = %s,
            role = %s,
            last_login_at = NOW(),
            updated_at = NOW()
        WHERE legacy_allowed_user_id = %s
        """,
        (supabase_user_id, effective_role, legacy_allowed_user_id),
    )
