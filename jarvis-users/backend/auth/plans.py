from fastapi import HTTPException

from backend.auth.current_user import get_current_user_id
from backend.auth.service import _serialize_profile
from backend.core.database import get_connection


PLAN_COPY = {
    "free": {
        "name": "Gratis",
        "tagline": "Organizá y entendé tus números.",
        "features": ["Resumen financiero", "Ingresos y gastos", "Deudas", "Metas", "Transacciones", "Horas extra"],
    },
    "basic": {
        "name": "Basic",
        "tagline": "JARVIS empieza a recomendar qué hacer.",
        "features": ["Todo Gratis", "Estrategia determinística de deudas", "Prioridades financieras", "Recomendaciones básicas"],
    },
    "vip": {
        "name": "VIP",
        "tagline": "La base del futuro Director Financiero Personal.",
        "features": ["Todo Basic", "Estrategia dinámica", "Proyecciones", "Metas inteligentes", "Escenarios financieros"],
    },
}

PLAN_RANK = {"free": 1, "basic": 2, "vip": 3}


def get_available_plans():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT code, name FROM plans WHERE code IN ('free','basic','vip') AND is_active=TRUE ORDER BY CASE code WHEN 'free' THEN 1 WHEN 'basic' THEN 2 ELSE 3 END"
        ).fetchall()
    return [{"code": row["code"], **PLAN_COPY[row["code"]]} for row in rows]


def select_plan(plan_code: str):
    user_id = get_current_user_id()
    if plan_code not in PLAN_COPY:
        raise HTTPException(status_code=400, detail="Plan no válido.")

    with get_connection() as conn:
        plan = conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE", (plan_code,)).fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="El plan seleccionado no está disponible.")

        profile_state = conn.execute(
            "SELECT onboarding_level FROM profiles WHERE id=%s FOR UPDATE",
            (user_id,),
        ).fetchone()
        completed_level = (profile_state or {}).get("onboarding_level") or "none"
        completed_rank = PLAN_RANK.get(completed_level, 0)
        needs_onboarding = completed_rank < PLAN_RANK[plan_code]

        # Billing comes later. Free is immediately active; paid plans remain pending
        # without blocking development access until the billing gate is implemented.
        status = "active" if plan_code == "free" else "pending"
        conn.execute(
            """INSERT INTO subscriptions (user_id, plan_id, status, created_at, updated_at)
               VALUES (%s,%s,%s,NOW(),NOW())
               ON CONFLICT (user_id) DO UPDATE SET plan_id=EXCLUDED.plan_id, status=EXCLUDED.status,
                   started_at=NULL, expires_at=NULL, last_payment_at=NULL, updated_at=NOW()""",
            (user_id, plan["id"], status),
        )
        conn.execute(
            """UPDATE profiles
               SET plan_selected=TRUE, onboarding_completed=%s, updated_at=NOW()
               WHERE id=%s""",
            (not needs_onboarding, user_id),
        )
        conn.commit()
        row = conn.execute(
            """SELECT id, supabase_user_id, email, display_name, role, status, onboarding_completed,
                      onboarding_level, plan_selected, created_at, updated_at, last_login_at FROM profiles WHERE id=%s""",
            (user_id,),
        ).fetchone()
        subscription = conn.execute(
            """SELECT s.id, p.code AS plan, s.status, s.started_at, s.expires_at, s.last_payment_at
               FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.user_id=%s""",
            (user_id,),
        ).fetchone()

    profile = _serialize_profile(row)
    profile["subscription"] = subscription
    return {"status": "ok", "profile": profile}


def require_feature(feature_code: str):
    user_id = get_current_user_id()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT 1
               FROM subscriptions s
               JOIN plan_features pf ON pf.plan_id=s.plan_id AND pf.enabled=TRUE
               JOIN features f ON f.id=pf.feature_id
               WHERE s.user_id=%s
                 AND f.code=%s
                 AND (
                     COALESCE(s.access_source, 'self_service') <> 'courtesy'
                     OR (
                         s.status='active'
                         AND s.expires_at IS NOT NULL
                         AND s.expires_at > NOW()
                     )
                 )""",
            (user_id, feature_code),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Esta función no está incluida en tu plan.")
