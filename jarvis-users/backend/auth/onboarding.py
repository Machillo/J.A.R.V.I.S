from fastapi import HTTPException

from backend.auth.current_user import get_current_user, get_current_user_id
from backend.auth.models import OnboardingRequest
from backend.auth.plans import PLAN_RANK
from backend.auth.service import _serialize_profile
from backend.core.database import get_connection


def _validate_for_plan(plan: str, request: OnboardingRequest) -> None:
    if plan in {"basic", "vip"}:
        if request.essential_monthly_expenses is None:
            raise HTTPException(status_code=422, detail="Indicá tus gastos esenciales mensuales aproximados.")
        if request.liquid_savings is None:
            raise HTTPException(status_code=422, detail="Indicá cuánto ahorro líquido tenés actualmente. Puede ser 0.")
        if request.emergency_fund_target is None:
            raise HTTPException(status_code=422, detail="Indicá tu objetivo de fondo de emergencia. Puede ser 0 por ahora.")

    if plan == "vip":
        if request.strategy_preference is None:
            raise HTTPException(status_code=422, detail="Elegí qué querés priorizar en tu estrategia VIP.")
        if request.discretionary_monthly_minimum is None:
            raise HTTPException(status_code=422, detail="Indicá cuánto querés reservar como mínimo para gastos personales. Puede ser 0.")


def get_onboarding_status():
    user_id = get_current_user_id()
    with get_connection() as conn:
        financial = conn.execute(
            """SELECT income_type, fixed_monthly_salary, hourly_rate, work_days_per_week,
                      hours_per_day, pay_frequency, payday_note, essential_monthly_expenses,
                      liquid_savings, emergency_fund_target, strategy_preference,
                      discretionary_monthly_minimum, created_at, updated_at
               FROM financial_profiles WHERE user_id=%s""",
            (user_id,),
        ).fetchone()
        debts = conn.execute(
            """SELECT id, name, total_amount, remaining_amount, monthly_payment,
                      interest_rate, payment_day
               FROM debts WHERE user_id=%s ORDER BY id""",
            (user_id,),
        ).fetchall()
        goals = conn.execute(
            """SELECT id, name, target_amount, current_amount, target_date, priority, status
               FROM financial_goals WHERE user_id=%s AND status='active' ORDER BY id""",
            (user_id,),
        ).fetchall()
    current = get_current_user()
    return {
        "completed": bool(current["onboarding_completed"]),
        "onboarding_level": current.get("onboarding_level"),
        "plan": (current.get("subscription") or {}).get("plan"),
        "financial_profile": financial,
        "debts": debts,
        "goals": goals,
    }


def complete_onboarding(request: OnboardingRequest):
    user_id = get_current_user_id()

    with get_connection() as conn:
        profile = conn.execute(
            "SELECT id, onboarding_completed, onboarding_level, plan_selected FROM profiles WHERE id=%s FOR UPDATE",
            (user_id,),
        ).fetchone()
        if not profile:
            raise HTTPException(status_code=404, detail="Perfil no encontrado.")
        if not profile["plan_selected"]:
            raise HTTPException(status_code=428, detail="Elegí un plan antes de completar el onboarding.")

        subscription = conn.execute(
            """SELECT p.code AS plan
               FROM subscriptions s JOIN plans p ON p.id=s.plan_id
               WHERE s.user_id=%s""",
            (user_id,),
        ).fetchone()
        plan = (subscription or {}).get("plan")
        if plan not in PLAN_RANK:
            raise HTTPException(status_code=409, detail="No pudimos determinar tu plan actual.")

        completed_level = profile.get("onboarding_level") or "none"
        if profile["onboarding_completed"] and PLAN_RANK.get(completed_level, 0) >= PLAN_RANK[plan]:
            raise HTTPException(status_code=409, detail="El onboarding requerido para este plan ya fue completado.")

        _validate_for_plan(plan, request)

        existing_debt_count = conn.execute("SELECT COUNT(*) AS count FROM debts WHERE user_id=%s", (user_id,)).fetchone()["count"]
        existing_goal_count = conn.execute("SELECT COUNT(*) AS count FROM financial_goals WHERE user_id=%s AND status='active'", (user_id,)).fetchone()["count"]
        if plan in {"basic", "vip"} and request.has_debts and existing_debt_count == 0 and not request.debts:
            raise HTTPException(status_code=422, detail="Agregá al menos una deuda o indicá que no tenés deudas.")
        if plan == "vip" and request.has_goals and existing_goal_count == 0 and not request.goals:
            raise HTTPException(status_code=422, detail="Agregá al menos una meta o indicá que no tenés metas activas.")

        conn.execute(
            """INSERT INTO financial_profiles (
                    user_id, income_type, fixed_monthly_salary, hourly_rate,
                    work_days_per_week, hours_per_day, pay_frequency, payday_note,
                    essential_monthly_expenses, liquid_savings, emergency_fund_target,
                    strategy_preference, discretionary_monthly_minimum,
                    created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    income_type=EXCLUDED.income_type,
                    fixed_monthly_salary=EXCLUDED.fixed_monthly_salary,
                    hourly_rate=EXCLUDED.hourly_rate,
                    work_days_per_week=EXCLUDED.work_days_per_week,
                    hours_per_day=EXCLUDED.hours_per_day,
                    pay_frequency=EXCLUDED.pay_frequency,
                    payday_note=EXCLUDED.payday_note,
                    essential_monthly_expenses=COALESCE(EXCLUDED.essential_monthly_expenses, financial_profiles.essential_monthly_expenses),
                    liquid_savings=COALESCE(EXCLUDED.liquid_savings, financial_profiles.liquid_savings),
                    emergency_fund_target=COALESCE(EXCLUDED.emergency_fund_target, financial_profiles.emergency_fund_target),
                    strategy_preference=COALESCE(EXCLUDED.strategy_preference, financial_profiles.strategy_preference),
                    discretionary_monthly_minimum=COALESCE(EXCLUDED.discretionary_monthly_minimum, financial_profiles.discretionary_monthly_minimum),
                    updated_at=NOW()
                RETURNING user_id""",
            (
                user_id,
                request.income_type,
                request.fixed_monthly_salary if request.income_type == "fixed" else None,
                request.hourly_rate if request.income_type == "hourly" else None,
                request.work_days_per_week,
                request.hours_per_day if request.income_type == "hourly" else None,
                request.pay_frequency,
                (request.payday_note or "").strip() or None,
                request.essential_monthly_expenses,
                request.liquid_savings,
                request.emergency_fund_target,
                request.strategy_preference,
                request.discretionary_monthly_minimum,
            ),
        )

        for debt in request.debts:
            conn.execute(
                """INSERT INTO debts (
                        user_id, name, total_amount, remaining_amount,
                        monthly_payment, interest_rate, payment_day
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    user_id,
                    debt.name.strip(),
                    debt.total_amount,
                    debt.remaining_amount,
                    debt.monthly_payment,
                    debt.interest_rate,
                    debt.payment_day,
                ),
            )

        for goal in request.goals:
            conn.execute(
                """INSERT INTO financial_goals (
                        user_id, name, target_amount, current_amount, target_date, priority
                    ) VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    user_id,
                    goal.name.strip(),
                    goal.target_amount,
                    goal.current_amount,
                    goal.target_date,
                    goal.priority,
                ),
            )

        conn.execute(
            """UPDATE profiles
               SET onboarding_completed=TRUE, onboarding_level=%s, updated_at=NOW()
               WHERE id=%s""",
            (plan, user_id),
        )
        conn.commit()

        row = conn.execute(
            """SELECT id, supabase_user_id, email, display_name, role, status,
                      onboarding_completed, onboarding_level, plan_selected, created_at, updated_at, last_login_at
               FROM profiles WHERE id=%s""",
            (user_id,),
        ).fetchone()

    response_profile = _serialize_profile(row)
    response_profile["subscription"] = subscription
    return {
        "status": "ok",
        "profile": response_profile,
    }
