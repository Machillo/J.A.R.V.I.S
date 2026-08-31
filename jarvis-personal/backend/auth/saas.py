from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_user, get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection

PLAN_COPY = {
    "free": {"name": "Gratis", "tagline": "Organizá y entendé tus números.", "features": ["Resumen financiero", "Ingresos y gastos", "Deudas", "Metas", "Transacciones", "Horas extra"]},
    "basic": {"name": "Basic", "tagline": "JARVIS empieza a recomendar qué hacer.", "features": ["Todo Gratis", "Estrategia determinística", "Prioridades financieras", "Recomendaciones"]},
    "vip": {"name": "VIP", "tagline": "Director financiero personal.", "features": ["Todo Basic", "Estrategia dinámica", "Proyecciones", "Metas inteligentes", "Escenarios"]},
}
PLAN_RANK = {"free": 1, "basic": 2, "vip": 3}


def _subscription(conn, account_id: str):
    row = conn.execute(
        """SELECT s.id, p.code AS plan, p.name AS plan_name,
                  CASE WHEN s.access_source='courtesy' AND s.expires_at IS NOT NULL AND s.expires_at<=NOW() THEN 'expired' ELSE s.status END AS status,
                  s.access_source, s.started_at, s.expires_at, s.last_payment_at,
                  s.courtesy_note, s.granted_by, s.granted_at
           FROM account_subscriptions s JOIN plans p ON p.id=s.plan_id
           WHERE s.account_id=%s""",
        (account_id,),
    ).fetchone()
    return row


def ensure_default_subscription(conn, account_id: str, role: str = "user"):
    existing = _subscription(conn, account_id)
    if existing:
        return existing
    plan_code = "vip" if role == "owner" else "free"
    source = "owner" if role == "owner" else "self_service"
    plan = conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE", (plan_code,)).fetchone()
    if not plan:
        raise HTTPException(status_code=500, detail="Ejecutá 20260831_unified_saas_foundation.sql antes de iniciar sesión.")
    conn.execute(
        """INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,created_at,updated_at)
           VALUES(%s,%s,'active',%s,NOW(),NOW(),NOW())""",
        (account_id, plan["id"], source),
    )
    return _subscription(conn, account_id)


def enrich_identity(user: dict[str, Any]) -> dict[str, Any]:
    account_id = str(user["account_id"])
    with get_connection() as conn:
        account = conn.execute(
            """SELECT onboarding_completed,onboarding_level,plan_selected,display_name FROM accounts WHERE id=%s""",
            (account_id,),
        ).fetchone()
        subscription = ensure_default_subscription(conn, account_id, user.get("role") or "user")
        conn.commit()
    return {
        **user,
        "display_name": (account or {}).get("display_name"),
        "onboarding_completed": bool((account or {}).get("onboarding_completed")),
        "onboarding_level": (account or {}).get("onboarding_level"),
        "plan_selected": bool((account or {}).get("plan_selected")),
        "subscription": subscription,
    }


def get_available_plans():
    with get_connection() as conn:
        rows = conn.execute("SELECT code FROM plans WHERE code IN ('free','basic','vip') AND is_active=TRUE ORDER BY CASE code WHEN 'free' THEN 1 WHEN 'basic' THEN 2 ELSE 3 END").fetchall()
    return [{"code": r["code"], **PLAN_COPY[r["code"]]} for r in rows]


def select_plan(plan_code: str):
    if plan_code not in PLAN_COPY:
        raise HTTPException(status_code=400, detail="Plan no válido.")
    user = get_current_user()
    if user.get("role") == "owner":
        return {"status": "ok", "profile": enrich_identity(user)}
    account_id = get_current_account_id()
    with get_connection() as conn:
        plan = conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE", (plan_code,)).fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan no disponible.")
        current = conn.execute("SELECT onboarding_level FROM accounts WHERE id=%s FOR UPDATE", (account_id,)).fetchone()
        completed = (current or {}).get("onboarding_level")
        needs = PLAN_RANK.get(completed or "", 0) < PLAN_RANK[plan_code]
        conn.execute(
            """INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,expires_at,courtesy_note,granted_by,granted_at,created_at,updated_at)
               VALUES(%s,%s,%s,'self_service',NOW(),NULL,NULL,NULL,NULL,NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET plan_id=EXCLUDED.plan_id,status=EXCLUDED.status,
                   access_source='self_service',started_at=NOW(),expires_at=NULL,courtesy_note=NULL,granted_by=NULL,granted_at=NULL,updated_at=NOW()""",
            (account_id, plan["id"], "active" if (plan_code == "free" or not needs) else "pending"),
        )
        conn.execute(
            "UPDATE accounts SET plan_selected=TRUE,onboarding_completed=%s,updated_at=NOW() WHERE id=%s",
            (not needs, account_id),
        )
        conn.commit()
    return {"status": "ok", "profile": enrich_identity(get_current_user())}


def get_onboarding_status():
    user = enrich_identity(get_current_user())
    with get_connection() as conn:
        profile = conn.execute("SELECT * FROM financial_profiles WHERE account_id=%s", (user["account_id"],)).fetchone()
    return {"profile": user, "financial_profile": profile}


def complete_onboarding(payload):
    user = get_current_user()
    if user.get("role") == "owner":
        return {"status": "ok", "profile": enrich_identity(user)}
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    subscription_plan = None
    with get_connection() as conn:
        sub = _subscription(conn, account_id)
        subscription_plan = (sub or {}).get("plan") or "free"
        if subscription_plan not in PLAN_COPY:
            raise HTTPException(status_code=409, detail="Seleccioná un plan primero.")
        if payload.income_type == "fixed" and payload.fixed_monthly_salary is None:
            raise HTTPException(status_code=422, detail="Indicá tu salario mensual.")
        if payload.income_type == "hourly" and (payload.hourly_rate is None or payload.hours_per_day is None):
            raise HTTPException(status_code=422, detail="Indicá tarifa por hora y horas por día.")
        if subscription_plan in {"basic","vip"} and payload.essential_monthly_expenses is None:
            raise HTTPException(status_code=422, detail="Basic/VIP requiere un estimado de gastos esenciales.")
        if subscription_plan == "vip" and not payload.strategy_preference:
            raise HTTPException(status_code=422, detail="VIP requiere una prioridad estratégica inicial.")
        conn.execute(
            """INSERT INTO financial_profiles(account_id,workspace_id,income_type,fixed_monthly_salary,hourly_rate,work_days_per_week,hours_per_day,pay_frequency,payday_note,essential_monthly_expenses,liquid_savings,emergency_fund_target,strategy_preference,discretionary_monthly_minimum,created_at,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET workspace_id=EXCLUDED.workspace_id,income_type=EXCLUDED.income_type,
                 fixed_monthly_salary=EXCLUDED.fixed_monthly_salary,hourly_rate=EXCLUDED.hourly_rate,work_days_per_week=EXCLUDED.work_days_per_week,
                 hours_per_day=EXCLUDED.hours_per_day,pay_frequency=EXCLUDED.pay_frequency,payday_note=EXCLUDED.payday_note,
                 essential_monthly_expenses=EXCLUDED.essential_monthly_expenses,liquid_savings=EXCLUDED.liquid_savings,
                 emergency_fund_target=EXCLUDED.emergency_fund_target,strategy_preference=EXCLUDED.strategy_preference,
                 discretionary_monthly_minimum=EXCLUDED.discretionary_monthly_minimum,updated_at=NOW()
               RETURNING account_id""",
            (account_id, workspace_id, payload.income_type, payload.fixed_monthly_salary if payload.income_type=='fixed' else None,
             payload.hourly_rate if payload.income_type=='hourly' else None, payload.work_days_per_week,
             payload.hours_per_day if payload.income_type=='hourly' else None, payload.pay_frequency,
             (payload.payday_note or '').strip() or None, payload.essential_monthly_expenses, payload.liquid_savings,
             payload.emergency_fund_target, payload.strategy_preference, payload.discretionary_monthly_minimum),
        )
        # Basic/VIP upgrades are intentionally pending until their required
        # onboarding is completed. Reaching this point means the profile was
        # validated and persisted, so activate the selected self-service plan.
        conn.execute(
            """UPDATE account_subscriptions
               SET status='active', started_at=COALESCE(started_at,NOW()), updated_at=NOW()
               WHERE account_id=%s AND access_source='self_service'""",
            (account_id,),
        )
        conn.execute(
            "UPDATE accounts SET onboarding_completed=TRUE,onboarding_level=%s,plan_selected=TRUE,updated_at=NOW() WHERE id=%s",
            (subscription_plan, account_id),
        )
        conn.commit()
    return {"status": "ok", "profile": enrich_identity(get_current_user())}


def require_feature(feature_code: str):
    user = get_current_user()
    if user.get("role") == "owner":
        return True
    account_id = get_current_account_id()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT 1 FROM account_subscriptions s
               JOIN plan_features pf ON pf.plan_id=s.plan_id AND pf.enabled=TRUE
               JOIN features f ON f.id=pf.feature_id
               WHERE s.account_id=%s AND f.code=%s
                 AND s.status='active'
                 AND (s.access_source<>'courtesy' OR (s.expires_at IS NOT NULL AND s.expires_at>NOW()))""",
            (account_id, feature_code),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Esta función no está incluida en tu plan.")
    return True


def list_managed_users(search: str | None = None):
    params=[]; where=""
    if search:
        needle=f"%{search.strip().lower()}%"; params=[needle,needle]
        where="WHERE LOWER(a.primary_email) LIKE %s OR LOWER(COALESCE(a.display_name,'')) LIKE %s"
    with get_connection() as conn:
        rows=conn.execute(
            f"""SELECT a.id,a.primary_email AS email,a.display_name,a.role,a.status,a.onboarding_completed,a.onboarding_level,a.plan_selected,
                       a.created_at,a.last_login_at,p.code AS plan,
                       CASE WHEN s.access_source='courtesy' AND s.expires_at IS NOT NULL AND s.expires_at<=NOW() THEN 'expired' ELSE s.status END AS subscription_status,
                       s.access_source,s.started_at,s.expires_at,s.courtesy_note,s.granted_at
                FROM accounts a LEFT JOIN account_subscriptions s ON s.account_id=a.id LEFT JOIN plans p ON p.id=s.plan_id
                {where} ORDER BY a.created_at DESC LIMIT 100""", tuple(params)).fetchall()
    return rows


def get_managed_user(account_id: str):
    with get_connection() as conn:
        row=conn.execute(
            """SELECT a.id,a.primary_email AS email,a.display_name,a.role,a.status,a.onboarding_completed,a.onboarding_level,a.plan_selected,
                      a.created_at,a.last_login_at,p.code AS plan,
                      CASE WHEN s.access_source='courtesy' AND s.expires_at IS NOT NULL AND s.expires_at<=NOW() THEN 'expired' ELSE s.status END AS subscription_status,
                      s.access_source,s.started_at,s.expires_at,s.courtesy_note,s.granted_at
               FROM accounts a LEFT JOIN account_subscriptions s ON s.account_id=a.id LEFT JOIN plans p ON p.id=s.plan_id
               WHERE a.id=%s""", (account_id,)).fetchone()
    if not row: raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return row


def grant_courtesy(account_id: str, plan_code: str, days: int, note: str | None = None):
    if plan_code not in {"basic","vip"}: raise HTTPException(status_code=400, detail="La cortesía solo puede ser Basic o VIP.")
    if days<1 or days>3650: raise HTTPException(status_code=400, detail="Duración inválida.")
    owner=get_current_user(); owner_id=get_current_account_id()
    if account_id==owner_id: raise HTTPException(status_code=400, detail="El owner ya tiene acceso total.")
    try: UUID(account_id)
    except ValueError as exc: raise HTTPException(status_code=400, detail="Cuenta inválida.") from exc
    with get_connection() as conn:
        target=conn.execute("SELECT id,role,status FROM accounts WHERE id=%s FOR UPDATE",(account_id,)).fetchone()
        if not target: raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if target["role"]=='owner': raise HTTPException(status_code=400, detail="No se asigna cortesía al owner.")
        if target["status"]!='active': raise HTTPException(status_code=409, detail="La cuenta no está activa.")
        plan=conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE",(plan_code,)).fetchone()
        conn.execute(
            """INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,expires_at,courtesy_note,granted_by,granted_at,created_at,updated_at)
               VALUES(%s,%s,'active','courtesy',NOW(),NOW()+(%s*INTERVAL '1 day'),%s,%s,NOW(),NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET plan_id=EXCLUDED.plan_id,status='active',access_source='courtesy',started_at=NOW(),
                 expires_at=NOW()+(%s*INTERVAL '1 day'),courtesy_note=EXCLUDED.courtesy_note,granted_by=EXCLUDED.granted_by,granted_at=NOW(),updated_at=NOW()""",
            (account_id,plan["id"],days,(note or '').strip()[:500] or None,owner_id,days),)
        conn.execute("UPDATE accounts SET plan_selected=TRUE,updated_at=NOW() WHERE id=%s",(account_id,)); conn.commit()
    return get_managed_user(account_id)


def revoke_courtesy(account_id: str):
    with get_connection() as conn:
        current=conn.execute("SELECT access_source FROM account_subscriptions WHERE account_id=%s FOR UPDATE",(account_id,)).fetchone()
        if not current or current["access_source"]!='courtesy': raise HTTPException(status_code=409, detail="La cuenta no tiene una cortesía activa.")
        free=conn.execute("SELECT id FROM plans WHERE code='free' AND is_active=TRUE").fetchone()
        conn.execute("""UPDATE account_subscriptions SET plan_id=%s,status='active',access_source='self_service',started_at=NOW(),expires_at=NULL,courtesy_note=NULL,granted_by=NULL,granted_at=NULL,updated_at=NOW() WHERE account_id=%s""",(free["id"],account_id)); conn.commit()
    return get_managed_user(account_id)
