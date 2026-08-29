from fastapi import HTTPException

from backend.core.database import get_connection
from backend.auth.owner_bridge import bind_owner_to_personal


VALID_PLANS = {"free", "basic", "vip"}
VALID_PROFILE_STATUSES = {"active", "blocked"}
MAX_COURTESY_DAYS = 3650


def _subscription_select():
    return """
        pl.code AS plan,
        CASE
            WHEN s.access_source = 'courtesy'
             AND s.expires_at IS NOT NULL
             AND s.expires_at <= NOW()
            THEN 'expired'
            ELSE s.status
        END AS subscription_status,
        s.started_at, s.expires_at, s.last_payment_at,
        COALESCE(s.access_source, 'self_service') AS access_source,
        s.courtesy_note, s.granted_by, s.granted_at
    """


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
                   {_subscription_select()}
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
            f"""
            SELECT p.id, p.supabase_user_id, p.email, p.display_name, p.role, p.status,
                   p.onboarding_completed, p.onboarding_level, p.plan_selected,
                   p.created_at, p.updated_at, p.last_login_at,
                   {_subscription_select()}
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
                INSERT INTO subscriptions (
                    user_id, plan_id, status, access_source,
                    started_at, expires_at, courtesy_note, granted_by, granted_at,
                    created_at, updated_at
                )
                VALUES (%s,%s,%s,'self_service',NULL,NULL,NULL,NULL,NULL,NOW(),NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    plan_id=EXCLUDED.plan_id,
                    status=EXCLUDED.status,
                    access_source='self_service',
                    started_at=NULL,
                    expires_at=NULL,
                    courtesy_note=NULL,
                    granted_by=NULL,
                    granted_at=NULL,
                    updated_at=NOW()
                """,
                (user_id, plan_row["id"], subscription_status),
            )
            conn.execute("UPDATE profiles SET plan_selected=TRUE, updated_at=NOW() WHERE id=%s", (user_id,))

        conn.commit()
    return get_user(user_id)


def grant_courtesy_access(
    user_id: int,
    *,
    plan: str,
    days: int,
    granted_by: str,
    note: str | None = None,
):
    if plan not in {"basic", "vip"}:
        raise HTTPException(status_code=400, detail="La cortesía solo puede ser Basic o VIP.")
    if days < 1 or days > MAX_COURTESY_DAYS:
        raise HTTPException(status_code=400, detail=f"La cortesía debe durar entre 1 y {MAX_COURTESY_DAYS} días.")

    clean_note = (note or "").strip()[:500] or None
    clean_granted_by = (granted_by or "owner").strip()[:160]

    with get_connection() as conn:
        profile = conn.execute(
            "SELECT id, role, status FROM profiles WHERE id=%s FOR UPDATE",
            (user_id,),
        ).fetchone()
        if not profile:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if profile["role"] == "owner":
            raise HTTPException(status_code=400, detail="No hace falta asignar cortesía al owner.")
        if profile["status"] != "active":
            raise HTTPException(status_code=409, detail="Activá el usuario antes de asignarle una cortesía.")

        plan_row = conn.execute(
            "SELECT id FROM plans WHERE code=%s AND is_active=TRUE",
            (plan,),
        ).fetchone()
        if not plan_row:
            raise HTTPException(status_code=404, detail="Plan no disponible.")

        conn.execute(
            """
            INSERT INTO subscriptions (
                user_id, plan_id, status, access_source,
                started_at, expires_at, courtesy_note, granted_by, granted_at,
                created_at, updated_at
            )
            VALUES (
                %s, %s, 'active', 'courtesy',
                NOW(), NOW() + (%s * INTERVAL '1 day'), %s, %s, NOW(),
                NOW(), NOW()
            )
            ON CONFLICT (user_id) DO UPDATE SET
                plan_id=EXCLUDED.plan_id,
                status='active',
                access_source='courtesy',
                started_at=NOW(),
                expires_at=NOW() + (%s * INTERVAL '1 day'),
                courtesy_note=EXCLUDED.courtesy_note,
                granted_by=EXCLUDED.granted_by,
                granted_at=NOW(),
                updated_at=NOW()
            """,
            (user_id, plan_row["id"], days, clean_note, clean_granted_by, days),
        )
        conn.execute(
            "UPDATE profiles SET plan_selected=TRUE, updated_at=NOW() WHERE id=%s",
            (user_id,),
        )
        conn.commit()

    return get_user(user_id)


def revoke_courtesy_access(user_id: int):
    with get_connection() as conn:
        subscription = conn.execute(
            "SELECT id, access_source FROM subscriptions WHERE user_id=%s FOR UPDATE",
            (user_id,),
        ).fetchone()
        if not subscription:
            raise HTTPException(status_code=404, detail="El usuario no tiene suscripción.")
        if subscription["access_source"] != "courtesy":
            raise HTTPException(status_code=409, detail="La suscripción actual no es una cortesía.")

        free_plan = conn.execute(
            "SELECT id FROM plans WHERE code='free' AND is_active=TRUE"
        ).fetchone()
        if not free_plan:
            raise HTTPException(status_code=500, detail="El plan Free no está disponible.")

        conn.execute(
            """
            UPDATE subscriptions
            SET plan_id=%s,
                status='active',
                access_source='self_service',
                started_at=NOW(),
                expires_at=NULL,
                courtesy_note=NULL,
                granted_by=NULL,
                granted_at=NULL,
                updated_at=NOW()
            WHERE user_id=%s
            """,
            (free_plan["id"], user_id),
        )
        conn.commit()

    return get_user(user_id)


def link_owner_personal_identity(personal_supabase_user_id: str):
    return bind_owner_to_personal(personal_supabase_user_id)
