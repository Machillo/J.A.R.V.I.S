from fastapi import HTTPException

from backend.core.database import get_connection
from backend.auth.owner_bridge import bind_owner_to_personal


VALID_PLANS = {"free", "basic", "vip"}
VALID_PROFILE_STATUSES = {"active", "blocked"}


def list_users(search: str | None = None):
    params = []
    where = ""
    if search:
        where = "WHERE LOWER(p.email) LIKE %s OR LOWER(COALESCE(p.display_name,'')) LIKE %s"
        needle = f"%{search.strip().lower()}%"
        params.extend([needle, needle])

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT p.id, p.supabase_user_id, p.email, p.display_name, p.role, p.status,
                   p.onboarding_completed, p.onboarding_level, p.plan_selected,
                   p.created_at, p.updated_at, p.last_login_at,
                   pl.code AS plan, s.status AS subscription_status,
                   s.started_at, s.expires_at, s.last_payment_at
            FROM profiles p
            LEFT JOIN subscriptions s ON s.user_id=p.id
            LEFT JOIN plans pl ON pl.id=s.plan_id
            {where}
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT 100
            """,
            tuple(params),
        ).fetchall()
    return rows


def get_user(user_id: int):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT p.id, p.supabase_user_id, p.email, p.display_name, p.role, p.status,
                   p.onboarding_completed, p.onboarding_level, p.plan_selected,
                   p.created_at, p.updated_at, p.last_login_at,
                   pl.code AS plan, s.status AS subscription_status,
                   s.started_at, s.expires_at, s.last_payment_at
            FROM profiles p
            LEFT JOIN subscriptions s ON s.user_id=p.id
            LEFT JOIN plans pl ON pl.id=s.plan_id
            WHERE p.id=%s
            """,
            (user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return row


def update_user_access(user_id: int, *, plan: str | None = None, status: str | None = None):
    if plan is not None and plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail="Plan no válido.")
    if status is not None and status not in VALID_PROFILE_STATUSES:
        raise HTTPException(status_code=400, detail="Estado no válido.")

    with get_connection() as conn:
        profile = conn.execute("SELECT id, role FROM profiles WHERE id=%s FOR UPDATE", (user_id,)).fetchone()
        if not profile:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        if status is not None:
            if profile["role"] == "owner" and status != "active":
                raise HTTPException(status_code=400, detail="El owner no puede ser bloqueado.")
            conn.execute("UPDATE profiles SET status=%s, updated_at=NOW() WHERE id=%s", (status, user_id))

        if plan is not None:
            plan_row = conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE", (plan,)).fetchone()
            if not plan_row:
                raise HTTPException(status_code=404, detail="Plan no disponible.")
            subscription_status = "active" if plan == "free" else "pending"
            conn.execute(
                """
                INSERT INTO subscriptions (user_id, plan_id, status, created_at, updated_at)
                VALUES (%s,%s,%s,NOW(),NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    plan_id=EXCLUDED.plan_id,
                    status=EXCLUDED.status,
                    updated_at=NOW()
                """,
                (user_id, plan_row["id"], subscription_status),
            )
            conn.execute("UPDATE profiles SET plan_selected=TRUE, updated_at=NOW() WHERE id=%s", (user_id,))

        conn.commit()
    return get_user(user_id)


def link_owner_personal_identity(personal_supabase_user_id: str):
    return bind_owner_to_personal(personal_supabase_user_id)
