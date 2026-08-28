from datetime import date

from fastapi import HTTPException

from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection
from backend.finance.strategy_engine import build_basic_strategy, build_vip_strategy


def _today(value: str | None = None) -> str:
    return value or date.today().isoformat()


def _sum(rows, key="amount") -> float:
    return round(sum(float(row.get(key) or 0) for row in rows), 2)


def get_income():
    user_id = get_current_user_id()
    with get_connection() as conn:
        return conn.execute(
            """SELECT id, amount, description, category, entry_date, created_at
               FROM income_entries WHERE user_id = %s ORDER BY entry_date DESC, id DESC""",
            (user_id,),
        ).fetchall()


def add_income(amount: float, description: str = "", category: str = "general", entry_date: str | None = None):
    user_id = get_current_user_id()
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO income_entries (user_id, amount, description, category, entry_date)
               VALUES (%s, %s, %s, %s, %s) RETURNING id, amount, description, category, entry_date, created_at""",
            (user_id, amount, description, category, _today(entry_date)),
        ).fetchone()
        conn.commit()
    return row


def get_expenses():
    user_id = get_current_user_id()
    with get_connection() as conn:
        return conn.execute(
            """SELECT id, amount, description, category, expense_date, created_at
               FROM expenses WHERE user_id = %s ORDER BY expense_date DESC, id DESC""",
            (user_id,),
        ).fetchall()


def add_expense(amount: float, description: str = "", category: str = "general", expense_date: str | None = None):
    user_id = get_current_user_id()
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO expenses (user_id, amount, description, category, expense_date)
               VALUES (%s, %s, %s, %s, %s) RETURNING id, amount, description, category, expense_date, created_at""",
            (user_id, amount, description, category, _today(expense_date)),
        ).fetchone()
        conn.commit()
    return row


def get_overtime():
    user_id = get_current_user_id()
    with get_connection() as conn:
        return conn.execute(
            """SELECT id, hours, hourly_rate, multiplier, amount, work_date, notes, created_at
               FROM overtime_entries WHERE user_id = %s ORDER BY work_date DESC, id DESC""",
            (user_id,),
        ).fetchall()


def add_overtime(hours: float, hourly_rate: float, multiplier: float = 1.5, work_date: str | None = None, notes: str = ""):
    user_id = get_current_user_id()
    amount = round(hours * hourly_rate * multiplier, 2)
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO overtime_entries (user_id, hours, hourly_rate, multiplier, amount, work_date, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, hours, hourly_rate, multiplier, amount, work_date, notes, created_at""",
            (user_id, hours, hourly_rate, multiplier, amount, _today(work_date), notes),
        ).fetchone()
        conn.commit()
    return row


def get_debts():
    user_id = get_current_user_id()
    with get_connection() as conn:
        return conn.execute(
            """SELECT id, name, total_amount, remaining_amount, monthly_payment, interest_rate,
                      payment_day, created_at, updated_at
               FROM debts WHERE user_id = %s ORDER BY remaining_amount DESC, id DESC""",
            (user_id,),
        ).fetchall()


def add_debt(name: str, remaining_amount: float, total_amount: float | None = None, monthly_payment: float | None = None,
             interest_rate: float | None = None, payment_day: int | None = None):
    user_id = get_current_user_id()
    if total_amount is not None and remaining_amount > total_amount:
        raise HTTPException(status_code=400, detail="El saldo pendiente no puede superar el monto total.")
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO debts (user_id, name, total_amount, remaining_amount, monthly_payment, interest_rate, payment_day)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, name, total_amount, remaining_amount, monthly_payment, interest_rate, payment_day, created_at, updated_at""",
            (user_id, name, total_amount, remaining_amount, monthly_payment, interest_rate, payment_day),
        ).fetchone()
        conn.commit()
    return row


def update_debt(debt_id: int, **values):
    user_id = get_current_user_id()
    if values.get("total_amount") is not None and values["remaining_amount"] > values["total_amount"]:
        raise HTTPException(status_code=400, detail="El saldo pendiente no puede superar el monto total.")
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE debts SET name=%s, total_amount=%s, remaining_amount=%s, monthly_payment=%s,
                      interest_rate=%s, payment_day=%s, updated_at=NOW()
               WHERE id=%s AND user_id=%s
               RETURNING id, name, total_amount, remaining_amount, monthly_payment, interest_rate, payment_day, created_at, updated_at""",
            (values["name"], values["total_amount"], values["remaining_amount"], values["monthly_payment"],
             values["interest_rate"], values.get("payment_day"), debt_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Deuda no encontrada.")
        conn.commit()
    return row


def delete_debt(debt_id: int):
    user_id = get_current_user_id()
    with get_connection() as conn:
        result = conn.execute("DELETE FROM debts WHERE id=%s AND user_id=%s", (debt_id, user_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Deuda no encontrada.")
        conn.commit()
    return {"status": "ok"}


def register_debt_payment(debt_id: int, amount: float, payment_date: str | None = None, notes: str = ""):
    user_id = get_current_user_id()
    with get_connection() as conn:
        debt = conn.execute(
            "SELECT id, remaining_amount FROM debts WHERE id=%s AND user_id=%s FOR UPDATE",
            (debt_id, user_id),
        ).fetchone()
        if not debt:
            raise HTTPException(status_code=404, detail="Deuda no encontrada.")
        applied = min(float(amount), float(debt["remaining_amount"]))
        new_remaining = round(float(debt["remaining_amount"]) - applied, 2)
        conn.execute(
            """INSERT INTO debt_payments (user_id, debt_id, amount, payment_date, notes)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, debt_id, applied, _today(payment_date), notes),
        )
        conn.execute(
            "UPDATE debts SET remaining_amount=%s, updated_at=NOW() WHERE id=%s AND user_id=%s",
            (new_remaining, debt_id, user_id),
        )
        conn.commit()
    return {"status": "ok", "applied": applied, "remaining_amount": new_remaining}


def get_summary():
    user_id = get_current_user_id()
    month_start = date.today().replace(day=1).isoformat()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT
                   COALESCE((SELECT SUM(amount) FROM income_entries WHERE user_id=%s AND entry_date >= %s), 0) AS regular_income,
                   COALESCE((SELECT SUM(amount) FROM overtime_entries WHERE user_id=%s AND work_date >= %s), 0) AS overtime_income,
                   COALESCE((SELECT SUM(amount) FROM expenses WHERE user_id=%s AND expense_date >= %s), 0) AS expenses,
                   COALESCE((SELECT SUM(remaining_amount) FROM debts WHERE user_id=%s), 0) AS debt_balance,
                   COALESCE((SELECT SUM(monthly_payment) FROM debts WHERE user_id=%s), 0) AS debt_monthly
            """,
            (user_id, month_start, user_id, month_start, user_id, month_start, user_id, user_id),
        ).fetchone()

    regular_income = round(float(row["regular_income"] or 0), 2)
    overtime_income = round(float(row["overtime_income"] or 0), 2)
    expense_total = round(float(row["expenses"] or 0), 2)
    debt_total = round(float(row["debt_balance"] or 0), 2)
    debt_monthly = round(float(row["debt_monthly"] or 0), 2)
    total_income = round(regular_income + overtime_income, 2)
    available = round(total_income - expense_total - debt_monthly, 2)
    return {
        "month": date.today().strftime("%Y-%m"),
        "income": total_income,
        "regular_income": regular_income,
        "overtime_income": overtime_income,
        "expenses": expense_total,
        "debt_balance": debt_total,
        "debt_monthly": debt_monthly,
        "available_after_commitments": available,
    }

def _monthly_income_estimate(profile: dict | None) -> float:
    if not profile:
        return 0.0
    if profile.get("income_type") == "fixed":
        return round(float(profile.get("fixed_monthly_salary") or 0), 2)
    hourly = float(profile.get("hourly_rate") or 0)
    hours = float(profile.get("hours_per_day") or 0)
    days = float(profile.get("work_days_per_week") or 0)
    return round(hourly * hours * days * 52 / 12, 2)


def get_strategy_snapshot():
    user_id = get_current_user_id()
    with get_connection() as conn:
        profile = conn.execute(
            """SELECT income_type, fixed_monthly_salary, hourly_rate, work_days_per_week, hours_per_day,
                      essential_monthly_expenses, liquid_savings, emergency_fund_target,
                      strategy_preference, discretionary_monthly_minimum
               FROM financial_profiles WHERE user_id=%s""",
            (user_id,),
        ).fetchone()
        debts = conn.execute(
            """SELECT id, name, remaining_amount, monthly_payment, interest_rate, payment_day
               FROM debts WHERE user_id=%s AND remaining_amount > 0 ORDER BY id""",
            (user_id,),
        ).fetchall()
        goals = conn.execute(
            """SELECT id, name, target_amount, current_amount, target_date, priority
               FROM financial_goals WHERE user_id=%s AND status='active' ORDER BY priority, target_date NULLS LAST, id""",
            (user_id,),
        ).fetchall()
    return {
        "monthly_income_estimate": _monthly_income_estimate(profile),
        "essential_monthly_expenses": profile.get("essential_monthly_expenses") if profile else None,
        "liquid_savings": profile.get("liquid_savings") if profile else None,
        "emergency_fund_target": profile.get("emergency_fund_target") if profile else None,
        "strategy_preference": profile.get("strategy_preference") if profile else None,
        "discretionary_monthly_minimum": profile.get("discretionary_monthly_minimum") if profile else None,
        "debts": [dict(row) for row in debts],
        "goals": [dict(row) for row in goals],
    }


def get_strategy_basic(extra_monthly: float = 0):
    return build_basic_strategy(get_strategy_snapshot(), extra_monthly=extra_monthly)


def get_strategy_vip():
    return build_vip_strategy(get_strategy_snapshot())
