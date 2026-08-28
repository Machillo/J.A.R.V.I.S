from fastapi import HTTPException

from backend.auth.current_user import get_current_user, get_current_user_id
from backend.auth.models import FinancialSituationUpdateRequest
from backend.auth.plans import PLAN_RANK
from backend.core.database import get_connection


def _current_plan() -> str:
    plan = (get_current_user().get("subscription") or {}).get("plan") or "free"
    if plan not in PLAN_RANK:
        raise HTTPException(status_code=409, detail="No pudimos determinar tu plan actual.")
    return plan


def _read_situation(conn, user_id: int, plan: str):
    financial = conn.execute(
        """SELECT income_type, fixed_monthly_salary, hourly_rate, work_days_per_week,
                  hours_per_day, pay_frequency, payday_note, essential_monthly_expenses,
                  liquid_savings, emergency_fund_target, strategy_preference,
                  discretionary_monthly_minimum, updated_at
           FROM financial_profiles WHERE user_id=%s""",
        (user_id,),
    ).fetchone()
    debt_stats = conn.execute(
        """SELECT COUNT(*) AS count,
                  COALESCE(SUM(remaining_amount), 0) AS balance,
                  COUNT(*) FILTER (WHERE interest_rate IS NULL) AS missing_interest
           FROM debts WHERE user_id=%s""",
        (user_id,),
    ).fetchone()
    goal_stats = conn.execute(
        """SELECT COUNT(*) AS count,
                  COALESCE(SUM(target_amount), 0) AS target,
                  COALESCE(SUM(current_amount), 0) AS current
           FROM financial_goals WHERE user_id=%s AND status='active'""",
        (user_id,),
    ).fetchone()
    return {
        "plan": plan,
        "financial_profile": financial,
        "debts": debt_stats,
        "goals": goal_stats,
    }


def get_financial_situation():
    user_id = get_current_user_id()
    plan = _current_plan()
    with get_connection() as conn:
        return _read_situation(conn, user_id, plan)


def update_financial_situation(request: FinancialSituationUpdateRequest):
    user_id = get_current_user_id()
    plan = _current_plan()

    # The API enforces the same tier boundaries as the UI. Values learned on a
    # higher plan are preserved on downgrade, but lower plans cannot alter them.
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM financial_profiles WHERE user_id=%s FOR UPDATE",
            (user_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="No encontramos tu situación financiera.")

        essential = request.essential_monthly_expenses if PLAN_RANK[plan] >= PLAN_RANK["basic"] else existing.get("essential_monthly_expenses")
        savings = request.liquid_savings if PLAN_RANK[plan] >= PLAN_RANK["basic"] else existing.get("liquid_savings")
        emergency = request.emergency_fund_target if PLAN_RANK[plan] >= PLAN_RANK["basic"] else existing.get("emergency_fund_target")
        preference = request.strategy_preference if plan == "vip" else existing.get("strategy_preference")
        discretionary = request.discretionary_monthly_minimum if plan == "vip" else existing.get("discretionary_monthly_minimum")

        conn.execute(
            """UPDATE financial_profiles SET
                    income_type=%s,
                    fixed_monthly_salary=%s,
                    hourly_rate=%s,
                    work_days_per_week=%s,
                    hours_per_day=%s,
                    pay_frequency=%s,
                    payday_note=%s,
                    essential_monthly_expenses=%s,
                    liquid_savings=%s,
                    emergency_fund_target=%s,
                    strategy_preference=%s,
                    discretionary_monthly_minimum=%s,
                    updated_at=NOW()
               WHERE user_id=%s""",
            (
                request.income_type,
                request.fixed_monthly_salary if request.income_type == "fixed" else None,
                request.hourly_rate if request.income_type == "hourly" else None,
                request.work_days_per_week,
                request.hours_per_day if request.income_type == "hourly" else None,
                request.pay_frequency,
                (request.payday_note or "").strip() or None,
                essential,
                savings,
                emergency,
                preference,
                discretionary,
                user_id,
            ),
        )
        conn.commit()
        return {"status": "ok", **_read_situation(conn, user_id, plan)}
