from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_user_id, get_current_workspace_id
from backend.auth.saas import require_feature
from backend.core.database import get_connection
from backend.finance.service import (
    get_expenses,
    get_payroll_events,
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
    """Return/create the legacy users.id required by old financial FKs.

    Finva authorization is account/workspace based. Some historical Personal tables
    still require user_id -> users(id), while authentication uses allowed_users.
    This bridge is account-scoped by the authenticated account email and exists only
    to satisfy those legacy foreign keys.
    """
    account_id = get_current_account_id()
    with get_connection() as conn:
        account = conn.execute(
            "SELECT primary_email, display_name FROM accounts WHERE id=%s",
            (account_id,),
        ).fetchone()
        if not account:
            raise HTTPException(status_code=401, detail="Cuenta no encontrada.")

        email = (account.get("primary_email") or "").strip().lower()
        if not email:
            raise HTTPException(status_code=500, detail="La cuenta no tiene email principal.")

        existing = conn.execute(
            "SELECT id FROM users WHERE lower(email)=lower(%s) ORDER BY id LIMIT 1",
            (email,),
        ).fetchone()
        if existing:
            return int(existing["id"])

        created = conn.execute(
            """INSERT INTO users(email,name,country,timezone,created_at)
               VALUES(%s,%s,%s,%s,NOW()) RETURNING id""",
            (email, (account.get("display_name") or "Finva User").strip(), "Unknown", "UTC"),
        ).fetchone()
        conn.commit()
        return int(created["id"])


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _ensure_income_schema(conn) -> None:
    """Keep manual income compatible when a deployment precedes its migration."""
    conn.execute("ALTER TABLE salaries ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'Salario'")


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
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_income_schema(conn)
        rows = conn.execute(
            """SELECT id,amount,source,COALESCE(category,'Salario') category,user_id,workspace_id,created_at
               FROM salaries WHERE workspace_id=%s ORDER BY created_at DESC,id DESC""",
            (workspace_id,),
        ).fetchall()
    return [{**row,"description":row.get("source"),"entry_date":str(row.get("created_at") or "")[:10]} for row in rows]


def create_income(payload):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_income_schema(conn)
        row = conn.execute(
            """INSERT INTO salaries(user_id,workspace_id,amount,source,category,created_at)
               VALUES(%s,%s,%s,%s,%s,COALESCE(%s::date,CURRENT_DATE)+TIME '12:00')
               RETURNING id,amount,source,category,created_at""",
            (user_id, workspace_id, payload.amount, (payload.description or payload.category or "Ingreso").strip(),
             (payload.category or "Otros ingresos").strip(), payload.entry_date),
        ).fetchone()
        conn.commit()
    return {**row, "description": row.get("source"), "entry_date": str(row.get("created_at"))[:10]}


def update_income(income_id: int, payload):
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_income_schema(conn)
        row = conn.execute(
            """UPDATE salaries SET amount=%s,source=%s,category=%s,
                      created_at=COALESCE(%s::date,created_at::date)+TIME '12:00'
               WHERE id=%s AND workspace_id=%s
               RETURNING id,amount,source,category,created_at""",
            (payload.amount, (payload.description or payload.category or "Ingreso").strip(),
             (payload.category or "Otros ingresos").strip(), payload.entry_date, income_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ingreso no encontrado.")
        conn.commit()
    return {**row, "description": row.get("source"), "entry_date": str(row.get("created_at"))[:10]}


def delete_income(income_id: int):
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute("DELETE FROM salaries WHERE id=%s AND workspace_id=%s RETURNING id", (income_id, workspace_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ingreso no encontrado.")
        conn.commit()
    return {"status": "ok", "id": income_id}


def list_expenses():
    return [
        {**row, "entry_date": str(row.get("created_at") or "")[:10]}
        for row in get_expenses()
    ]


def create_expense_entry(payload):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    category = (payload.category or "Compras").strip()
    expense_type = expense_type_for_category(category)
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO expenses(category,expense_type,description,amount,user_id,workspace_id,created_at)
               VALUES(%s,%s,%s,%s,%s,%s,COALESCE(%s::date,CURRENT_DATE)+TIME '12:00')
               RETURNING id,category,expense_type,description,amount,user_id,workspace_id,created_at""",
            (category, expense_type, payload.description or "", payload.amount, user_id, workspace_id, payload.entry_date),
        ).fetchone()
        conn.commit()
    return {**row, "entry_date": payload.entry_date or str(row.get("created_at") or "")[:10]}


def update_expense(expense_id: int, payload):
    workspace_id = get_current_workspace_id()
    category = (payload.category or "Compras").strip()
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE expenses SET amount=%s,description=%s,category=%s,expense_type=%s,
                      created_at=COALESCE(%s::date,created_at::date)+TIME '12:00'
               WHERE id=%s AND workspace_id=%s
               RETURNING id,category,expense_type,description,amount,created_at""",
            (payload.amount, payload.description or "", category, expense_type_for_category(category),
             payload.entry_date, expense_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Gasto no encontrado.")
        conn.commit()
    return {**row, "entry_date": str(row.get("created_at"))[:10]}


def delete_expense(expense_id: int):
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute("DELETE FROM expenses WHERE id=%s AND workspace_id=%s RETURNING id", (expense_id, workspace_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Gasto no encontrado.")
        conn.commit()
    return {"status": "ok", "id": expense_id}


def list_overtime():
    return [row for row in get_payroll_events() if str(row.get("event_type") or "").lower() == "ot"]


def create_overtime(payload):
    user_id = get_current_user_id()
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
                   user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,interest_rate,
                   term_months,payment_day,created_at,first_payment_date,auto_update_monthly,
                   installments_paid,updated_at,start_date,next_payment_date,last_payment_date,
                   interest_method,fixed_fee_amount,workspace_id
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NULL,%s,0,NOW(),NULL,%s,NULL,'monthly',0,%s)
               RETURNING id,name,debt_type,total_amount,remaining_amount,monthly_payment,interest_rate,term_months,payment_day,next_payment_date,created_at""",
            (user_id, payload.name.strip(), payload.debt_type, max(total, remaining), remaining, monthly, interest,
             payload.term_months, payload.payment_day, monthly > 0, payload.next_payment_date, workspace_id),
        ).fetchone()
        conn.commit()
    return row


def pay_user_debt(debt_id: int, amount: float):
    user_id = _legacy_financial_user_id()
    workspace_id = get_current_workspace_id()
    payment = max(float(amount or 0), 0)
    if payment <= 0:
        raise HTTPException(status_code=400, detail="El pago debe ser mayor que cero.")
    with get_connection() as conn:
        debt = conn.execute(
            "SELECT id,name,remaining_amount,monthly_payment FROM debts WHERE id=%s AND workspace_id=%s",
            (debt_id, workspace_id),
        ).fetchone()
        if not debt:
            raise HTTPException(status_code=404, detail="Deuda no encontrada.")
        previous = _money(debt.get("remaining_amount"))
        applied = min(payment, previous)
        new_remaining = max(previous - applied, 0)
        conn.execute(
            "UPDATE debts SET remaining_amount=%s, updated_at=NOW() WHERE id=%s AND workspace_id=%s",
            (new_remaining, debt_id, workspace_id),
        )
        # Keep an auditable transaction; legacy user_id uses users(id), ownership uses workspace_id.
        conn.execute(
            """INSERT INTO transactions(
                   user_id,workspace_id,transaction_date,description,amount,transaction_type,category,account,source,notes,created_at
               ) VALUES(%s,%s,%s,%s,%s,'debt_payment',%s,NULL,'finva_debt_payment',%s,NOW())""",
            (user_id, workspace_id, date.today().isoformat(), f"Pago {debt['name']}", applied,
             debt["name"], f"debt_id:{debt_id}"),
        )
        conn.commit()
    return {"status": "OK", "debt_id": debt_id, "payment_amount": applied, "new_remaining_amount": new_remaining}



def list_user_debts():
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,name,debt_type,total_amount,remaining_amount,monthly_payment,interest_rate,
                      term_months,payment_day,next_payment_date,created_at,
                      CASE WHEN total_amount>0 THEN ROUND((1-(remaining_amount/total_amount))*100,1) ELSE 0 END AS progress_percent
               FROM debts WHERE workspace_id=%s ORDER BY id DESC""",
            (workspace_id,),
        ).fetchall()
    return rows


def update_user_debt(debt_id: int, payload):
    workspace_id = get_current_workspace_id()
    remaining = float(payload.remaining_amount or 0)
    total = max(float(payload.total_amount if payload.total_amount is not None else remaining), remaining)
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE debts SET name=%s,debt_type=%s,total_amount=%s,remaining_amount=%s,
                      monthly_payment=%s,interest_rate=%s,term_months=%s,payment_day=%s,
                      next_payment_date=%s,updated_at=NOW()
               WHERE id=%s AND workspace_id=%s
               RETURNING id,name,debt_type,total_amount,remaining_amount,monthly_payment,
                         interest_rate,term_months,payment_day,next_payment_date""",
            (payload.name.strip(), payload.debt_type, total, remaining, payload.monthly_payment or 0,
             payload.interest_rate, payload.term_months, payload.payment_day, payload.next_payment_date,
             debt_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Deuda no encontrada.")
        conn.commit()
    return row


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


def update_user_goal(goal_id: int, payload):
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE financial_goals SET name=%s,target_amount=%s,current_amount=%s,
                      target_date=%s,priority=%s,status=%s
               WHERE id=%s AND workspace_id=%s
               RETURNING id,name,target_amount,current_amount,target_date,priority,status,created_at""",
            (payload.name.strip(), payload.target_amount, min(payload.current_amount, payload.target_amount),
             payload.target_date, payload.priority, payload.status, goal_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Meta no encontrada.")
        conn.commit()
    return row


def contribute_user_goal(goal_id: int, payload):
    workspace_id = get_current_workspace_id()
    contribution_date = payload.contribution_date or date.today().isoformat()
    with get_connection() as conn:
        goal = conn.execute(
            "SELECT id,target_amount,current_amount FROM financial_goals WHERE id=%s AND workspace_id=%s FOR UPDATE",
            (goal_id, workspace_id),
        ).fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Meta no encontrada.")
        amount = min(float(payload.amount), max(float(goal['target_amount']) - float(goal['current_amount']), 0))
        if amount <= 0:
            raise HTTPException(status_code=409, detail="La meta ya está completa.")
        current = float(goal["current_amount"]) + amount
        status = "completed" if current >= float(goal["target_amount"]) else "active"
        conn.execute(
            "INSERT INTO finva_goal_contributions(workspace_id,goal_id,amount,contribution_date) VALUES(%s,%s,%s,%s)",
            (workspace_id, goal_id, amount, contribution_date),
        )
        row = conn.execute(
            """UPDATE financial_goals SET current_amount=%s,status=%s WHERE id=%s AND workspace_id=%s
               RETURNING id,name,target_amount,current_amount,target_date,priority,status""",
            (current, status, goal_id, workspace_id),
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
