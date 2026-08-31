from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_user, get_current_user_id, get_current_workspace_id
from backend.auth.saas import require_feature
from backend.core.database import get_connection
from backend.finance.service import (
    add_salary,
    delete_debt,
    get_debts,
    get_expenses,
    get_payroll_events,
    get_salaries,
)
from backend.finance.category_catalog import normalize_category, expense_type_for_category
from backend.user_product.strategy_engine import (
    build_basic_strategy,
    build_paycheck_plan,
    build_vip_insights,
    build_vip_scenario,
    build_vip_strategy,
)




def _legacy_financial_user_id() -> int:
    """Return a compatibility users.id for legacy financial FK columns.

    Finva ownership is enforced by workspace_id. Some legacy Personal tables still
    keep user_id foreign keys to users(id), while authentication is bridged through
    allowed_users. Provision the compatibility row lazily without changing Personal.
    """
    allowed_user_id = get_current_user_id()
    identity = get_current_user()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE allowed_user_id=%s ORDER BY id LIMIT 1",
            (allowed_user_id,),
        ).fetchone()
        if row:
            return int(row["id"])
        row = conn.execute(
            """INSERT INTO users(allowed_user_id,name,country,timezone,created_at)
               VALUES(%s,%s,'Unknown','UTC',NOW())
               RETURNING id""",
            (allowed_user_id, (identity.get("email") or "Finva user").strip()),
        ).fetchone()
        conn.commit()
    return int(row["id"])

def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _monthly_income_estimate(profile: dict | None) -> float:
    if not profile:
        return 0.0
    if profile.get("income_type") == "fixed":
        return _money(profile.get("fixed_monthly_salary"))
    hourly = _money(profile.get("hourly_rate"))
    hours = _money(profile.get("hours_per_day"))
    days = _money(profile.get("work_days_per_week"))
    return round(hourly * hours * days * 52 / 12, 2)


def get_user_finance_summary():
    workspace_id = get_current_workspace_id()
    month_start = date.today().replace(day=1)
    with get_connection() as conn:
        row = conn.execute(
            """SELECT
                 COALESCE((SELECT SUM(amount) FROM salaries WHERE workspace_id=%s AND created_at >= %s),0) AS regular_income,
                 COALESCE((SELECT SUM(amount) FROM payroll_events WHERE workspace_id=%s AND created_at >= %s AND amount > 0),0) AS overtime_income,
                 COALESCE((SELECT SUM(amount) FROM expenses WHERE workspace_id=%s AND created_at >= %s),0) AS expenses,
                 COALESCE((SELECT SUM(remaining_amount) FROM debts WHERE workspace_id=%s),0) AS debt_balance,
                 COALESCE((SELECT SUM(monthly_payment) FROM debts WHERE workspace_id=%s),0) AS debt_monthly""",
            (workspace_id, month_start, workspace_id, month_start, workspace_id, month_start, workspace_id, workspace_id),
        ).fetchone()
    regular = _money(row["regular_income"])
    overtime = _money(row["overtime_income"])
    expenses = _money(row["expenses"])
    debt_balance = _money(row["debt_balance"])
    debt_monthly = _money(row["debt_monthly"])
    income = round(regular + overtime, 2)
    return {
        "month": date.today().strftime("%Y-%m"),
        "income": income,
        "regular_income": regular,
        "overtime_income": overtime,
        "expenses": expenses,
        "debt_balance": debt_balance,
        "debt_monthly": debt_monthly,
        "available_after_commitments": round(income - expenses - debt_monthly, 2),
    }


def list_income():
    return [
        {
            **row,
            "description": row.get("source"),
            "category": "salario",
            "entry_date": str(row.get("created_at") or "")[:10],
        }
        for row in get_salaries()
    ]


def create_income(payload):
    result = add_salary(payload.amount, (payload.description or payload.category or "Ingreso").strip())
    return {**result, "description": result.get("source"), "category": payload.category, "entry_date": payload.entry_date}


def list_expenses():
    return [
        {**row, "entry_date": str(row.get("created_at") or "")[:10]}
        for row in get_expenses()
    ]


def create_expense_entry(payload):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    category = normalize_category(payload.category or "general", "expense")
    expense_type = expense_type_for_category(category)
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO expenses(category,expense_type,description,amount,user_id,workspace_id,created_at)
               VALUES(%s,%s,%s,%s,%s,%s,NOW())
               RETURNING id,category,expense_type,description,amount,user_id,workspace_id,created_at""",
            (category, expense_type, payload.description or "", payload.amount, user_id, workspace_id),
        ).fetchone()
        conn.commit()
    return {**row, "entry_date": payload.entry_date or str(row.get("created_at") or "")[:10]}


def list_overtime():
    return [row for row in get_payroll_events() if str(row.get("event_type") or "").lower() == "ot"]


def create_overtime(payload):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    amount = round(payload.hours * payload.hourly_rate * payload.multiplier, 2)
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO payroll_events(event_type,hours,multiplier,amount,description,user_id,workspace_id,created_at)
               VALUES('ot',%s,%s,%s,%s,%s,%s,NOW()) RETURNING id,created_at""",
            (payload.hours, payload.multiplier, amount, payload.notes or "", user_id, workspace_id),
        ).fetchone()
        conn.commit()
    return {
        "id": row["id"], "event_type": "ot", "hours": payload.hours,
        "hourly_rate": payload.hourly_rate, "multiplier": payload.multiplier,
        "amount": amount, "notes": payload.notes, "work_date": payload.work_date,
        "created_at": row["created_at"],
    }


def create_user_debt(payload):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    remaining = float(payload.remaining_amount or 0)
    total = float(payload.total_amount if payload.total_amount is not None else remaining)
    monthly = float(payload.monthly_payment or 0)
    interest = float(payload.interest_rate or 0)
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO debts(
                   name,debt_type,total_amount,remaining_amount,monthly_payment,interest_rate,
                   term_months,payment_day,start_date,first_payment_date,auto_update_monthly,
                   installments_paid,interest_method,fixed_fee_amount,user_id,workspace_id,created_at,updated_at
               ) VALUES(%s,'other',%s,%s,%s,%s,NULL,%s,CURRENT_DATE,CURRENT_DATE,%s,0,'monthly',0,%s,%s,NOW(),NOW())
               RETURNING id,name,total_amount,remaining_amount,monthly_payment,interest_rate,payment_day,created_at""",
            (payload.name.strip(), max(total, remaining), remaining, monthly, interest, payload.payment_day,
             monthly > 0, user_id, workspace_id),
        ).fetchone()
        conn.commit()
    return row


def pay_user_debt(debt_id: int, amount: float):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    payment = max(float(amount or 0), 0)
    if payment <= 0:
        raise HTTPException(status_code=422, detail="El pago debe ser mayor que cero.")
    with get_connection() as conn:
        debt = conn.execute(
            """SELECT id,name,remaining_amount,monthly_payment,installments_paid
               FROM debts WHERE id=%s AND workspace_id=%s FOR UPDATE""",
            (debt_id, workspace_id),
        ).fetchone()
        if not debt:
            raise HTTPException(status_code=404, detail="Deuda no encontrada.")
        previous = _money(debt.get("remaining_amount"))
        principal = min(payment, previous)
        remaining = round(max(previous - principal, 0), 2)
        monthly = _money(debt.get("monthly_payment"))
        conn.execute(
            "UPDATE debts SET remaining_amount=%s,updated_at=NOW() WHERE id=%s AND workspace_id=%s",
            (remaining, debt_id, workspace_id),
        )
        payment_row = conn.execute(
            """INSERT INTO debt_payments(
                   user_id,workspace_id,debt_id,payment_type,amount,previous_remaining_amount,new_remaining_amount,
                   previous_monthly_payment,new_monthly_payment,principal_amount,interest_amount,fee_amount,
                   extra_principal_amount,description,payment_date,installment_number,source,created_at
               ) VALUES(%s,%s,%s,'extra_payment',%s,%s,%s,%s,%s,%s,0,0,%s,%s,CURRENT_DATE,%s,'finva',NOW())
               RETURNING id""",
            (user_id, workspace_id, debt_id, principal, previous, remaining, monthly, monthly, principal, principal,
             "Pago registrado desde Finva", int(debt.get("installments_paid") or 0)),
        ).fetchone()
        conn.execute(
            """INSERT INTO transactions(
                   user_id,workspace_id,transaction_date,description,amount,transaction_type,category,account,source,notes,created_at
               ) VALUES(%s,%s,CURRENT_DATE,%s,%s,'debt_payment',%s,NULL,'finva',%s,NOW())""",
            (user_id, workspace_id, f"Pago {debt['name']}", principal, debt['name'], f"debt_id:{debt_id}"),
        )
        conn.commit()
    return {
        "status": "ok", "payment_id": payment_row["id"], "debt_id": debt_id,
        "payment_amount": principal, "new_remaining_amount": remaining,
    }



def list_user_debts():
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,name,total_amount,remaining_amount,monthly_payment,interest_rate,payment_day,created_at
               FROM debts WHERE workspace_id=%s ORDER BY id DESC""",
            (workspace_id,),
        ).fetchall()
    return rows


def delete_user_debt(debt_id: int):
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM debts WHERE id=%s AND workspace_id=%s RETURNING id",
            (debt_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Deuda no encontrada.")
        conn.commit()
    return {"status": "ok", "id": debt_id}


def list_user_goals():
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,name,target_amount,current_amount,target_date,priority,status,created_at
               FROM financial_goals WHERE workspace_id=%s ORDER BY id DESC""",
            (workspace_id,),
        ).fetchall()
    return rows


def create_user_goal(payload):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO financial_goals(name,target_amount,current_amount,target_date,priority,status,user_id,workspace_id,created_at)
               VALUES(%s,%s,%s,%s,%s,'active',%s,%s,NOW())
               RETURNING id,name,target_amount,current_amount,target_date,priority,status,created_at""",
            (payload.name.strip(), payload.target_amount, payload.current_amount, payload.target_date,
             payload.priority, user_id, workspace_id),
        ).fetchone()
        conn.commit()
    return row


def delete_user_goal(goal_id: int):
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM financial_goals WHERE id=%s AND workspace_id=%s RETURNING id",
            (goal_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Meta no encontrada.")
        conn.commit()
    return {"status": "ok", "id": goal_id}


def list_user_transactions():
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,transaction_date,description,amount,transaction_type,category,notes,created_at
               FROM transactions WHERE workspace_id=%s ORDER BY transaction_date DESC,id DESC""",
            (workspace_id,),
        ).fetchall()
    return rows


def create_user_transaction(payload):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    category = normalize_category(payload.category, payload.transaction_type)
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO transactions(transaction_date,description,amount,transaction_type,category,account,source,notes,user_id,workspace_id,created_at)
               VALUES(%s,%s,%s,%s,%s,'','finva',%s,%s,%s,NOW())
               RETURNING id,transaction_date,description,amount,transaction_type,category,notes,created_at""",
            (payload.transaction_date, payload.description.strip(), payload.amount, payload.transaction_type,
             category, payload.notes or "", user_id, workspace_id),
        ).fetchone()
        conn.commit()
    return row


def delete_user_transaction(transaction_id: int):
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM transactions WHERE id=%s AND workspace_id=%s RETURNING id",
            (transaction_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transacción no encontrada.")
        conn.commit()
    return {"status": "ok", "id": transaction_id}

def get_financial_situation():
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        profile = conn.execute(
            """SELECT income_type,fixed_monthly_salary,hourly_rate,work_days_per_week,hours_per_day,
                      pay_frequency,payday_note,essential_monthly_expenses,liquid_savings,
                      emergency_fund_target,strategy_preference,discretionary_monthly_minimum
               FROM financial_profiles WHERE account_id=%s AND workspace_id=%s""",
            (account_id, workspace_id),
        ).fetchone()
        debts = conn.execute(
            """SELECT COUNT(*) AS count, COALESCE(SUM(remaining_amount),0) AS balance,
                      COUNT(*) FILTER (WHERE interest_rate IS NULL OR interest_rate=0) AS missing_interest
               FROM debts WHERE workspace_id=%s AND remaining_amount>0""",
            (workspace_id,),
        ).fetchone()
        goals = conn.execute(
            """SELECT COUNT(*) AS count, COALESCE(SUM(current_amount),0) AS current,
                      COALESCE(SUM(target_amount),0) AS target
               FROM financial_goals WHERE workspace_id=%s AND status='active'""",
            (workspace_id,),
        ).fetchone()
    return {
        "financial_profile": dict(profile) if profile else None,
        "debts": dict(debts),
        "goals": dict(goals),
    }


def update_financial_situation(payload):
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO financial_profiles(
                 account_id,workspace_id,income_type,fixed_monthly_salary,hourly_rate,work_days_per_week,hours_per_day,
                 pay_frequency,payday_note,essential_monthly_expenses,liquid_savings,emergency_fund_target,
                 strategy_preference,discretionary_monthly_minimum,created_at,updated_at
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET
                 workspace_id=EXCLUDED.workspace_id,income_type=EXCLUDED.income_type,
                 fixed_monthly_salary=EXCLUDED.fixed_monthly_salary,hourly_rate=EXCLUDED.hourly_rate,
                 work_days_per_week=EXCLUDED.work_days_per_week,hours_per_day=EXCLUDED.hours_per_day,
                 pay_frequency=EXCLUDED.pay_frequency,payday_note=EXCLUDED.payday_note,
                 essential_monthly_expenses=EXCLUDED.essential_monthly_expenses,liquid_savings=EXCLUDED.liquid_savings,
                 emergency_fund_target=EXCLUDED.emergency_fund_target,strategy_preference=EXCLUDED.strategy_preference,
                 discretionary_monthly_minimum=EXCLUDED.discretionary_monthly_minimum,updated_at=NOW()
               RETURNING account_id""",
            (
                account_id, workspace_id, payload.income_type,
                payload.fixed_monthly_salary if payload.income_type == "fixed" else None,
                payload.hourly_rate if payload.income_type == "hourly" else None,
                payload.work_days_per_week,
                payload.hours_per_day if payload.income_type == "hourly" else None,
                payload.pay_frequency, (payload.payday_note or "").strip() or None,
                payload.essential_monthly_expenses, payload.liquid_savings, payload.emergency_fund_target,
                payload.strategy_preference, payload.discretionary_monthly_minimum,
            ),
        )
        conn.commit()
    return get_financial_situation()


def _strategy_snapshot():
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        profile = conn.execute(
            """SELECT income_type,fixed_monthly_salary,hourly_rate,work_days_per_week,hours_per_day,
                      essential_monthly_expenses,liquid_savings,emergency_fund_target,
                      strategy_preference,discretionary_monthly_minimum,pay_frequency,payday_note
               FROM financial_profiles WHERE account_id=%s AND workspace_id=%s""",
            (account_id, workspace_id),
        ).fetchone()
        debts = conn.execute(
            """SELECT id,name,remaining_amount,monthly_payment,NULLIF(interest_rate,0) AS interest_rate,payment_day
               FROM debts WHERE workspace_id=%s AND remaining_amount>0 ORDER BY id""",
            (workspace_id,),
        ).fetchall()
        goals = conn.execute(
            """SELECT id,name,target_amount,current_amount,target_date,priority
               FROM financial_goals WHERE workspace_id=%s AND status='active'
               ORDER BY priority,target_date NULLS LAST,id""",
            (workspace_id,),
        ).fetchall()
    profile_dict = dict(profile) if profile else None
    return {
        "monthly_income_estimate": _monthly_income_estimate(profile_dict),
        "essential_monthly_expenses": profile_dict.get("essential_monthly_expenses") if profile_dict else None,
        "liquid_savings": profile_dict.get("liquid_savings") if profile_dict else None,
        "emergency_fund_target": profile_dict.get("emergency_fund_target") if profile_dict else None,
        "strategy_preference": profile_dict.get("strategy_preference") if profile_dict else None,
        "discretionary_monthly_minimum": profile_dict.get("discretionary_monthly_minimum") if profile_dict else None,
        "pay_frequency": profile_dict.get("pay_frequency") if profile_dict else None,
        "payday_note": profile_dict.get("payday_note") if profile_dict else None,
        "debts": [dict(row) for row in debts],
        "goals": [dict(row) for row in goals],
    }


def get_strategy_basic(extra_monthly: float = 0):
    require_feature("strategy_basic")
    snapshot = _strategy_snapshot()
    strategy = build_basic_strategy(snapshot, extra_monthly=extra_monthly)
    return {**strategy, "next_paycheck": build_paycheck_plan(strategy, snapshot.get("pay_frequency"), vip=False)}


def get_strategy_vip():
    require_feature("strategy_vip")
    snapshot = _strategy_snapshot()
    strategy = build_vip_strategy(snapshot)
    return {**strategy, "insights": build_vip_insights(snapshot, strategy), "next_paycheck": build_paycheck_plan(strategy, snapshot.get("pay_frequency"), vip=True)}


def simulate_strategy_vip(monthly_income_change: float = 0, monthly_expense_change: float = 0, one_time_extra: float = 0):
    require_feature("strategy_vip")
    return build_vip_scenario(_strategy_snapshot(), monthly_income_change, monthly_expense_change, one_time_extra)
