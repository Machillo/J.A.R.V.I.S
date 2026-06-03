from backend.core.database import get_connection
from backend.auth.current_user import get_current_user_id


def add_salary(amount: float, source: str):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO salaries (amount, source, created_at)
            VALUES (?, ?, datetime('now'))
            """,
            (amount, source)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "amount": amount,
        "source": source
    }


def get_salaries():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, source, created_at
            FROM salaries
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def add_bonus(amount: float, description: str = ""):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bonuses (amount, description, created_at)
            VALUES (?, ?, datetime('now'))
            """,
            (amount, description)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "amount": amount,
        "description": description
    }


def get_bonuses():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, description, created_at
            FROM bonuses
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def add_debt(
    name: str,
    debt_type: str,
    total_amount: float,
    remaining_amount: float,
    monthly_payment: float,
    interest_rate: float = 0,
    term_months: int | None = None,
    payment_day: int | None = None
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO debts (
                name,
                debt_type,
                total_amount,
                remaining_amount,
                monthly_payment,
                interest_rate,
                term_months,
                payment_day,
                user_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                name,
                debt_type,
                total_amount,
                remaining_amount,
                monthly_payment,
                interest_rate,
                term_months,
                payment_day,
                user_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "debt_type": debt_type,
        "total_amount": total_amount,
        "remaining_amount": remaining_amount,
        "monthly_payment": monthly_payment,
        "interest_rate": interest_rate,
        "term_months": term_months,
        "payment_day": payment_day,
        "user_id": user_id
    }


def get_debts():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id,
                   name,
                   debt_type,
                   total_amount,
                   remaining_amount,
                   monthly_payment,
                   interest_rate,
                   term_months,
                   payment_day,
                   created_at,
                   user_id
            FROM debts
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def add_saving(name: str, amount: float):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO savings (
                name,
                amount,
                user_id,
                created_at
            )
            VALUES (?, ?, ?, datetime('now'))
            """,
            (
                name,
                amount,
                user_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "amount": amount,
        "user_id": user_id
    }


def get_savings():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id,
                   name,
                   amount,
                   created_at,
                   user_id
            FROM savings
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]

def update_saving(
    saving_id: int,
    name: str,
    amount: float
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        saving = conn.execute(
            """
            SELECT id
            FROM savings
            WHERE id = ?
            AND user_id = ?
            """,
            (saving_id, user_id)
        ).fetchone()

        if not saving:
            return {
                "message": "Ahorro no encontrado o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            UPDATE savings
            SET name = ?,
                amount = ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                name,
                amount,
                saving_id,
                user_id
            )
        )

        conn.commit()

    return {
        "message": "Ahorro actualizado correctamente.",
        "id": saving_id,
        "name": name,
        "amount": amount,
        "user_id": user_id,
        "status": "OK"
    }


def delete_saving(saving_id: int):
    user_id = get_current_user_id()

    with get_connection() as conn:
        saving = conn.execute(
            """
            SELECT id,
                   name,
                   amount,
                   created_at,
                   user_id
            FROM savings
            WHERE id = ?
            AND user_id = ?
            """,
            (saving_id, user_id)
        ).fetchone()

        if not saving:
            return {
                "message": "Ahorro no encontrado o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            DELETE FROM savings
            WHERE id = ?
            AND user_id = ?
            """,
            (saving_id, user_id)
        )

        conn.commit()

    return {
        "message": "Ahorro eliminado correctamente.",
        "deleted_saving": dict(saving),
        "status": "OK"
    }


def add_investment(name: str, amount: float):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO investments (
                name,
                amount,
                user_id,
                created_at
            )
            VALUES (?, ?, ?, datetime('now'))
            """,
            (
                name,
                amount,
                user_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "amount": amount,
        "user_id": user_id
    }


def get_investments():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id,
                   name,
                   amount,
                   created_at,
                   user_id
            FROM investments
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]

def update_investment(
    investment_id: int,
    name: str,
    amount: float
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        investment = conn.execute(
            """
            SELECT id
            FROM investments
            WHERE id = ?
            AND user_id = ?
            """,
            (investment_id, user_id)
        ).fetchone()

        if not investment:
            return {
                "message": "Inversión no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            UPDATE investments
            SET name = ?,
                amount = ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                name,
                amount,
                investment_id,
                user_id
            )
        )

        conn.commit()

    return {
        "message": "Inversión actualizada correctamente.",
        "id": investment_id,
        "name": name,
        "amount": amount,
        "user_id": user_id,
        "status": "OK"
    }


def delete_investment(investment_id: int):
    user_id = get_current_user_id()

    with get_connection() as conn:
        investment = conn.execute(
            """
            SELECT id,
                   name,
                   amount,
                   created_at,
                   user_id
            FROM investments
            WHERE id = ?
            AND user_id = ?
            """,
            (investment_id, user_id)
        ).fetchone()

        if not investment:
            return {
                "message": "Inversión no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            DELETE FROM investments
            WHERE id = ?
            AND user_id = ?
            """,
            (investment_id, user_id)
        )

        conn.commit()

    return {
        "message": "Inversión eliminada correctamente.",
        "deleted_investment": dict(investment),
        "status": "OK"
    }


def add_expense(
    category: str,
    amount: float,
    expense_type: str = "variable",
    description: str = ""
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO expenses (
                category,
                expense_type,
                description,
                amount,
                user_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                category,
                expense_type,
                description,
                amount,
                user_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "category": category,
        "expense_type": expense_type,
        "description": description,
        "amount": amount,
        "user_id": user_id
    }


def get_expenses():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id,
                   category,
                   expense_type,
                   description,
                   amount,
                   created_at,
                   user_id
            FROM expenses
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_financial_summary():
    user_id = get_current_user_id()

    salary_projection = calculate_monthly_salary_projection()

    if salary_projection.get("status") == "ERROR":
        projected_net_income = 0
        projected_gross_income = 0
        payroll_deductions_total = 0
    else:
        projected_net_income = salary_projection["results"]["projected_net"]
        projected_gross_income = salary_projection["adjustments"]["projected_gross"]
        payroll_deductions_total = salary_projection["deductions"]["total_deductions"]

    with get_connection() as conn:
        bonus_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM bonuses
            """
        ).fetchone()["total"]

        debt_total = conn.execute(
            """
            SELECT COALESCE(SUM(remaining_amount), 0) AS total
            FROM debts
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()["total"]

        monthly_debt_payments = conn.execute(
            """
            SELECT COALESCE(SUM(monthly_payment), 0) AS total
            FROM debts
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()["total"]

        savings_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM savings
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()["total"]

        investments_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM investments
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()["total"]

        fixed_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'fixed'
            AND user_id = ?
            """,
            (user_id,)
        ).fetchone()["total"]

        variable_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'variable'
            AND user_id = ?
            """,
            (user_id,)
        ).fetchone()["total"]

        one_time_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'one_time'
            AND user_id = ?
            """,
            (user_id,)
        ).fetchone()["total"]

    total_income = projected_net_income + bonus_total

    expenses_total = (
        fixed_expenses_total
        + variable_expenses_total
        + one_time_expenses_total
    )

    available_cash = total_income - monthly_debt_payments - expenses_total
    net_worth = savings_total + investments_total - debt_total

    return {
        "income": {
            "projected_gross_income": projected_gross_income,
            "payroll_deductions_total": payroll_deductions_total,
            "projected_net_income": projected_net_income,
            "bonus_total": bonus_total,
            "total_income": total_income
        },
        "debts": {
            "debt_total": debt_total,
            "monthly_debt_payments": monthly_debt_payments
        },
        "assets": {
            "savings_total": savings_total,
            "investments_total": investments_total
        },
        "expenses": {
            "fixed_expenses_total": fixed_expenses_total,
            "variable_expenses_total": variable_expenses_total,
            "one_time_expenses_total": one_time_expenses_total,
            "expenses_total": expenses_total
        },
        "results": {
            "available_cash": available_cash,
            "net_worth": net_worth
        },
        "user_id": user_id
    }

def check_spending(amount: float = 0):
    summary = get_financial_summary()
    available_cash = summary["results"]["available_cash"]

    if amount <= 0:
        return {
            "message": f"Según los datos registrados, puedes gastar hasta ₡{available_cash:,.2f}.",
            "available_cash": available_cash,
            "requested_amount": amount,
            "status": "INFO"
        }

    remaining_after_purchase = available_cash - amount

    if remaining_after_purchase < 0:
        return {
            "message": (
                f"No recomendado. Esa compra de ₡{amount:,.2f} excede tu disponible "
                f"por ₡{abs(remaining_after_purchase):,.2f}."
            ),
            "available_cash": available_cash,
            "requested_amount": amount,
            "remaining_after_purchase": remaining_after_purchase,
            "status": "RED"
        }

    if remaining_after_purchase <= available_cash * 0.2:
        return {
            "message": (
                f"Posible, pero riesgoso. Después de gastar ₡{amount:,.2f}, "
                f"te quedarían ₡{remaining_after_purchase:,.2f}."
            ),
            "available_cash": available_cash,
            "requested_amount": amount,
            "remaining_after_purchase": remaining_after_purchase,
            "status": "YELLOW"
        }

    return {
        "message": (
            f"Sí es posible. Después de gastar ₡{amount:,.2f}, "
            f"te quedarían ₡{remaining_after_purchase:,.2f}."
        ),
        "available_cash": available_cash,
        "requested_amount": amount,
        "remaining_after_purchase": remaining_after_purchase,
        "status": "GREEN"
    }

def set_employment_profile(
    hourly_rate: float,
    regular_hours_per_week: float,
    overtime_multiplier: float = 1.5,
    holiday_multiplier: float = 2
):
    with get_connection() as conn:
        conn.execute("DELETE FROM employment_profile")

        cursor = conn.execute(
            """
            INSERT INTO employment_profile (
                hourly_rate,
                regular_hours_per_week,
                overtime_multiplier,
                holiday_multiplier,
                created_at
            )
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (
                hourly_rate,
                regular_hours_per_week,
                overtime_multiplier,
                holiday_multiplier
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "hourly_rate": hourly_rate,
        "regular_hours_per_week": regular_hours_per_week,
        "overtime_multiplier": overtime_multiplier,
        "holiday_multiplier": holiday_multiplier
    }


def get_employment_profile():
    with get_connection() as conn:
        profile = conn.execute(
            """
            SELECT id, hourly_rate, regular_hours_per_week, overtime_multiplier, holiday_multiplier, created_at
            FROM employment_profile
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if not profile:
        return None

    return dict(profile)


def add_payroll_deduction(
    name: str,
    deduction_type: str,
    amount: float,
    frequency: str
):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO payroll_deductions (
                name,
                deduction_type,
                amount,
                frequency,
                created_at
            )
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (name, deduction_type, amount, frequency)
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "deduction_type": deduction_type,
        "amount": amount,
        "frequency": frequency
    }


def get_payroll_deductions():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, deduction_type, amount, frequency, created_at
            FROM payroll_deductions
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def add_payroll_event(
    event_type: str,
    hours: float,
    description: str = ""
):
    profile = get_employment_profile()

    if not profile:
        return {
            "message": "No existe perfil laboral configurado.",
            "status": "ERROR"
        }

    hourly_rate = profile["hourly_rate"]

    event_type = event_type.lower().strip()

    if event_type == "ot":
        multiplier = profile["overtime_multiplier"]
        amount = hours * hourly_rate * multiplier

    elif event_type == "holiday":
        multiplier = profile["holiday_multiplier"]
        amount = hours * hourly_rate * multiplier

    elif event_type == "vgh":
        multiplier = -1
        amount = hours * hourly_rate * multiplier

    else:
        multiplier = 1
        amount = hours * hourly_rate

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO payroll_events (
                event_type,
                hours,
                multiplier,
                amount,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                event_type,
                hours,
                multiplier,
                amount,
                description
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "event_type": event_type,
        "hours": hours,
        "multiplier": multiplier,
        "amount": amount,
        "description": description
    }


def get_payroll_events():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, event_type, hours, multiplier, amount, description, created_at
            FROM payroll_events
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def calculate_monthly_salary_projection():
    profile = get_employment_profile()

    if not profile:
        return {
            "message": "No existe perfil laboral configurado.",
            "status": "ERROR"
        }

    hourly_rate = profile["hourly_rate"]
    weekly_hours = profile["regular_hours_per_week"]

    base_monthly_gross = hourly_rate * weekly_hours * 4.333

    with get_connection() as conn:
        payroll_events_total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payroll_events"
        ).fetchone()["total"]

        deductions = conn.execute(
            """
            SELECT name, deduction_type, amount, frequency
            FROM payroll_deductions
            """
        ).fetchall()

    projected_gross = base_monthly_gross + payroll_events_total

    total_deductions = 0

    deduction_details = []

    for deduction in deductions:
        amount = deduction["amount"]
        frequency = deduction["frequency"]
        deduction_type = deduction["deduction_type"]

        if deduction_type == "percentage":
            calculated_amount = projected_gross * (amount / 100)

        else:
            if frequency == "weekly":
                calculated_amount = amount * 4.333
            else:
                calculated_amount = amount

        total_deductions += calculated_amount

        deduction_details.append({
            "name": deduction["name"],
            "deduction_type": deduction_type,
            "base_amount": amount,
            "frequency": frequency,
            "calculated_monthly_amount": calculated_amount
        })

    projected_net = projected_gross - total_deductions

    return {
        "base": {
            "hourly_rate": hourly_rate,
            "regular_hours_per_week": weekly_hours,
            "base_monthly_gross": base_monthly_gross
        },
        "adjustments": {
            "payroll_events_total": payroll_events_total,
            "projected_gross": projected_gross
        },
        "deductions": {
            "total_deductions": total_deductions,
            "details": deduction_details
        },
        "results": {
            "projected_net": projected_net
        }
    }

def delete_expense(expense_id: int):
    user_id = get_current_user_id()

    with get_connection() as conn:
        expense = conn.execute(
            """
            SELECT id,
                   category,
                   expense_type,
                   amount,
                   description,
                   user_id
            FROM expenses
            WHERE id = ?
            AND user_id = ?
            """,
            (expense_id, user_id)
        ).fetchone()

        if not expense:
            return {
                "message": "Gasto no encontrado o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            DELETE FROM expenses
            WHERE id = ?
            AND user_id = ?
            """,
            (expense_id, user_id)
        )

        conn.commit()

    return {
        "message": "Gasto eliminado correctamente.",
        "deleted_expense": dict(expense),
        "status": "OK"
    }


def update_expense(
    expense_id: int,
    category: str,
    amount: float,
    expense_type: str,
    description: str = ""
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        expense = conn.execute(
            """
            SELECT id
            FROM expenses
            WHERE id = ?
            AND user_id = ?
            """,
            (expense_id, user_id)
        ).fetchone()

        if not expense:
            return {
                "message": "Gasto no encontrado o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            UPDATE expenses
            SET category = ?,
                amount = ?,
                expense_type = ?,
                description = ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                category,
                amount,
                expense_type,
                description,
                expense_id,
                user_id
            )
        )

        conn.commit()

    return {
        "message": "Gasto actualizado correctamente.",
        "id": expense_id,
        "category": category,
        "amount": amount,
        "expense_type": expense_type,
        "description": description,
        "user_id": user_id,
        "status": "OK"
    }

def delete_debt(debt_id: int):
    user_id = get_current_user_id()

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id,
                   name,
                   debt_type,
                   total_amount,
                   remaining_amount,
                   monthly_payment,
                   interest_rate,
                   term_months,
                   payment_day,
                   user_id
            FROM debts
            WHERE id = ?
            AND user_id = ?
            """,
            (debt_id, user_id)
        ).fetchone()

        if not debt:
            return {
                "message": "Deuda no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            DELETE FROM debt_payments
            WHERE debt_id = ?
            """,
            (debt_id,)
        )

        conn.execute(
            """
            DELETE FROM debts
            WHERE id = ?
            AND user_id = ?
            """,
            (debt_id, user_id)
        )

        conn.commit()

    return {
        "message": "Deuda eliminada correctamente.",
        "deleted_debt": dict(debt),
        "status": "OK"
    }


def update_debt(
    debt_id: int,
    name: str,
    debt_type: str,
    total_amount: float,
    remaining_amount: float,
    monthly_payment: float,
    interest_rate: float = 0,
    term_months: int | None = None,
    payment_day: int | None = None
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id
            FROM debts
            WHERE id = ?
            AND user_id = ?
            """,
            (debt_id, user_id)
        ).fetchone()

        if not debt:
            return {
                "message": "Deuda no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        conn.execute(
            """
            UPDATE debts
            SET name = ?,
                debt_type = ?,
                total_amount = ?,
                remaining_amount = ?,
                monthly_payment = ?,
                interest_rate = ?,
                term_months = ?,
                payment_day = ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                name,
                debt_type,
                total_amount,
                remaining_amount,
                monthly_payment,
                interest_rate,
                term_months,
                payment_day,
                debt_id,
                user_id
            )
        )

        conn.commit()

    return {
        "message": "Deuda actualizada correctamente.",
        "id": debt_id,
        "name": name,
        "debt_type": debt_type,
        "total_amount": total_amount,
        "remaining_amount": remaining_amount,
        "monthly_payment": monthly_payment,
        "interest_rate": interest_rate,
        "term_months": term_months,
        "payment_day": payment_day,
        "user_id": user_id,
        "status": "OK"
    }


def apply_extra_payment_to_debt(
    debt_id: int,
    amount: float,
    new_remaining_amount: float | None = None,
    new_monthly_payment: float | None = None,
    description: str = ""
):
    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount,
                   monthly_payment, interest_rate, term_months, payment_day
            FROM debts
            WHERE id = ?
            """,
            (debt_id,)
        ).fetchone()

        if not debt:
            return {
                "message": "Deuda no encontrada.",
                "status": "ERROR"
            }

        previous_remaining_amount = debt["remaining_amount"]
        previous_monthly_payment = debt["monthly_payment"]

        final_remaining_amount = (
            new_remaining_amount
            if new_remaining_amount is not None
            else max(previous_remaining_amount - amount, 0)
        )

        final_monthly_payment = (
            new_monthly_payment
            if new_monthly_payment is not None
            else previous_monthly_payment
        )

        conn.execute(
            """
            UPDATE debts
            SET remaining_amount = ?, monthly_payment = ?
            WHERE id = ?
            """,
            (
                final_remaining_amount,
                final_monthly_payment,
                debt_id
            )
        )

        cursor = conn.execute(
            """
            INSERT INTO debt_payments (
                debt_id,
                payment_type,
                amount,
                previous_remaining_amount,
                new_remaining_amount,
                previous_monthly_payment,
                new_monthly_payment,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                debt_id,
                "extra_payment",
                amount,
                previous_remaining_amount,
                final_remaining_amount,
                previous_monthly_payment,
                final_monthly_payment,
                description
            )
        )

        conn.commit()

    return {
        "message": "Abono extraordinario aplicado correctamente.",
        "payment_id": cursor.lastrowid,
        "debt_id": debt_id,
        "debt_name": debt["name"],
        "payment_amount": amount,
        "previous_remaining_amount": previous_remaining_amount,
        "new_remaining_amount": final_remaining_amount,
        "previous_monthly_payment": previous_monthly_payment,
        "new_monthly_payment": final_monthly_payment,
        "status": "OK"
    }

def get_debt_by_name(name: str):
    user_id = get_current_user_id()

    search = f"%{name.lower()}%"

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id,
                   name,
                   total_amount,
                   remaining_amount,
                   monthly_payment,
                   interest_rate,
                   created_at,
                   user_id
            FROM debts
            WHERE lower(name) LIKE ?
            AND user_id = ?
            LIMIT 1
            """,
            (search, user_id)
        ).fetchone()

    if not debt:
        return {
            "message": f"No encontré una deuda que coincida con '{name}'.",
            "status": "ERROR"
        }

    debt = dict(debt)

    return {
        "message": (
            f"De la deuda {debt['name']} debes ₡{debt['remaining_amount']:,.2f}. "
            f"La cuota mensual registrada es ₡{debt['monthly_payment']:,.2f}."
        ),
        "debt": debt,
        "status": "OK"
    }

def apply_monthly_payment_to_debt(
    debt_id: int,
    amount: float,
    new_remaining_amount: float,
    new_monthly_payment: float | None = None,
    description: str = ""
):
    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount,
                   monthly_payment, interest_rate, term_months, payment_day
            FROM debts
            WHERE id = ?
            """,
            (debt_id,)
        ).fetchone()

        if not debt:
            return {
                "message": "Deuda no encontrada.",
                "status": "ERROR"
            }

        previous_remaining_amount = debt["remaining_amount"]
        previous_monthly_payment = debt["monthly_payment"]

        final_monthly_payment = (
            new_monthly_payment
            if new_monthly_payment is not None
            else previous_monthly_payment
        )

        conn.execute(
            """
            UPDATE debts
            SET remaining_amount = ?, monthly_payment = ?
            WHERE id = ?
            """,
            (
                new_remaining_amount,
                final_monthly_payment,
                debt_id
            )
        )

        cursor = conn.execute(
            """
            INSERT INTO debt_payments (
                debt_id,
                payment_type,
                amount,
                previous_remaining_amount,
                new_remaining_amount,
                previous_monthly_payment,
                new_monthly_payment,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                debt_id,
                "monthly_payment",
                amount,
                previous_remaining_amount,
                new_remaining_amount,
                previous_monthly_payment,
                final_monthly_payment,
                description
            )
        )

        conn.commit()

    return {
        "message": "Pago mensual registrado correctamente.",
        "payment_id": cursor.lastrowid,
        "debt_id": debt_id,
        "debt_name": debt["name"],
        "payment_amount": amount,
        "previous_remaining_amount": previous_remaining_amount,
        "new_remaining_amount": new_remaining_amount,
        "previous_monthly_payment": previous_monthly_payment,
        "new_monthly_payment": final_monthly_payment,
        "status": "OK"
    }


def get_debt_payments(debt_id: int | None = None):
    with get_connection() as conn:
        if debt_id:
            rows = conn.execute(
                """
                SELECT id, debt_id, payment_type, amount, previous_remaining_amount,
                       new_remaining_amount, previous_monthly_payment,
                       new_monthly_payment, description, created_at
                FROM debt_payments
                WHERE debt_id = ?
                ORDER BY id DESC
                """,
                (debt_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, debt_id, payment_type, amount, previous_remaining_amount,
                       new_remaining_amount, previous_monthly_payment,
                       new_monthly_payment, description, created_at
                FROM debt_payments
                ORDER BY id DESC
                """
            ).fetchall()

    return [dict(row) for row in rows]

def get_net_worth_report():
    user_id = get_current_user_id()

    with get_connection() as conn:
        savings = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id
            FROM savings
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

        investments = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id
            FROM investments
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

        debts = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount,
                   monthly_payment, interest_rate, term_months,
                   payment_day, created_at, user_id
            FROM debts
            WHERE user_id = ?
            ORDER BY remaining_amount DESC
            """,
            (user_id,)
        ).fetchall()

    savings_list = [dict(row) for row in savings]
    investments_list = [dict(row) for row in investments]
    debts_list = [dict(row) for row in debts]

    savings_total = sum(item["amount"] for item in savings_list)
    investments_total = sum(item["amount"] for item in investments_list)
    assets_total = savings_total + investments_total

    debt_total = sum(item["remaining_amount"] for item in debts_list)
    monthly_debt_payments = sum(item["monthly_payment"] for item in debts_list)

    net_worth = assets_total - debt_total

    if net_worth < 0:
        status = "negative"
        interpretation = (
            "Tu patrimonio neto es negativo porque tus deudas registradas "
            "son mayores que tus activos registrados."
        )
    elif net_worth == 0:
        status = "neutral"
        interpretation = (
            "Tu patrimonio neto está en cero. Tus activos registrados cubren "
            "exactamente tus deudas registradas."
        )
    else:
        status = "positive"
        interpretation = (
            "Tu patrimonio neto es positivo. Tus activos registrados superan "
            "tus deudas registradas."
        )

    if debt_total > 0 and assets_total == 0:
        risk_level = "high"
        priority = (
            "Registrar activos reales si existen y priorizar reducción de deuda."
        )
    elif debt_total > assets_total:
        risk_level = "medium_high"
        priority = (
            "Reducir deudas de mayor interés y aumentar activos líquidos."
        )
    elif debt_total == 0:
        risk_level = "low"
        priority = (
            "Mantener activos, crear fondo de emergencia e invertir de forma ordenada."
        )
    else:
        risk_level = "medium"
        priority = (
            "Mantener control de deuda y seguir aumentando patrimonio."
        )

    if assets_total > 0:
        debt_to_asset_ratio = debt_total / assets_total
    else:
        debt_to_asset_ratio = None

    highest_debt = debts_list[0] if debts_list else None

    recommendations = []

    if assets_total == 0:
        recommendations.append(
            "Registrar ahorros, inversiones o saldos disponibles reales para que el patrimonio sea más preciso."
        )

    if highest_debt:
        recommendations.append(
            f"Priorizar seguimiento de la deuda más grande: {highest_debt['name']} por ₡{highest_debt['remaining_amount']:,.2f}."
        )

    high_interest_debts = [
        debt for debt in debts_list
        if debt["interest_rate"] and debt["interest_rate"] >= 20
    ]

    if high_interest_debts:
        recommendations.append(
            "Revisar deudas con interés alto para aplicar estrategia de avalancha o refinanciamiento."
        )

    if monthly_debt_payments > 0:
        recommendations.append(
            f"Tus pagos mensuales de deuda registrados suman aproximadamente ₡{monthly_debt_payments:,.2f}."
        )

    return {
        "assets": {
            "savings": savings_list,
            "investments": investments_list,
            "savings_total": savings_total,
            "investments_total": investments_total,
            "assets_total": assets_total
        },
        "liabilities": {
            "debts": debts_list,
            "debt_total": debt_total,
            "monthly_debt_payments": monthly_debt_payments,
            "highest_debt": highest_debt,
            "high_interest_debts": high_interest_debts
        },
        "net_worth": net_worth,
        "status": status,
        "risk_level": risk_level,
        "interpretation": interpretation,
        "priority": priority,
        "recommendations": recommendations,
        "ratios": {
            "debt_to_asset_ratio": debt_to_asset_ratio
        },
        "user_id": user_id
    }

def get_user_status():
    summary = get_financial_summary()
    net_worth = get_net_worth_report()

    user_id = get_current_user_id()

    with get_connection() as conn:
        goals = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date,
                   priority, status, created_at, user_id
            FROM financial_goals
            WHERE status = 'active'
            AND user_id = ?
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                    ELSE 5
                END,
                target_date ASC
            """,
            (user_id,)
        ).fetchall()

    goals_list = [dict(row) for row in goals]

    active_goals_count = len(goals_list)
    critical_goals = [
        goal for goal in goals_list
        if goal["priority"] == "critical"
    ]

    total_goals_remaining = sum(
        max(goal["target_amount"] - goal["current_amount"], 0)
        for goal in goals_list
    )

    most_urgent_goal = goals_list[0] if goals_list else None

    return {
        "income": {
            "monthly_net_income": summary["income"]["projected_net_income"],
            "total_income": summary["income"]["total_income"]
        },

        "assets": {
            "savings": net_worth["assets"]["savings_total"],
            "investments": net_worth["assets"]["investments_total"],
            "assets_total": net_worth["assets"]["assets_total"],
            "net_worth": net_worth["net_worth"]
        },

        "debts": {
            "total": net_worth["liabilities"]["debt_total"],
            "monthly_payments": net_worth["liabilities"]["monthly_debt_payments"],
            "highest_debt": (
                net_worth["liabilities"]["highest_debt"]["name"]
                if net_worth["liabilities"]["highest_debt"]
                else None
            )
        },

        "expenses": {
            "fixed_expenses": summary["expenses"]["fixed_expenses_total"],
            "total_expenses": summary["expenses"]["expenses_total"]
        },

        "cashflow": {
            "available_cash": summary["results"]["available_cash"]
        },

        "goals": {
            "active_goals_count": active_goals_count,
            "critical_goals_count": len(critical_goals),
            "total_goals_remaining": total_goals_remaining,
            "most_urgent_goal": most_urgent_goal,
            "active_goals": goals_list
        },

        "financial_health": {
            "status": net_worth["status"],
            "risk_level": net_worth["risk_level"]
        },
        "user_id": user_id
    }

def get_financial_dashboard():
    user_status = get_user_status()
    net_worth = get_net_worth_report()

    income = user_status["income"]
    expenses = user_status["expenses"]
    debts = user_status["debts"]
    cashflow = user_status["cashflow"]
    goals = user_status["goals"]
    financial_health = user_status["financial_health"]

    alerts = []
    quick_recommendations = []

    if financial_health["risk_level"] == "high":
        alerts.append({
            "type": "risk",
            "level": "high",
            "message": "Tu riesgo financiero está alto por patrimonio neto negativo y deudas activas."
        })

    if cashflow["available_cash"] < 100000:
        alerts.append({
            "type": "cashflow",
            "level": "medium",
            "message": "Tu efectivo disponible estimado es menor a ₡100,000."
        })

    if goals["critical_goals_count"] > 0:
        alerts.append({
            "type": "goal",
            "level": "high",
            "message": "Tienes una meta crítica activa que requiere seguimiento."
        })

    if debts["monthly_payments"] > 0:
        quick_recommendations.append(
            "Mantener pagos mínimos y priorizar deudas con mayor interés."
        )

    if goals["most_urgent_goal"]:
        quick_recommendations.append(
            f"Revisar progreso de la meta: {goals['most_urgent_goal']['name']}."
        )

    if cashflow["available_cash"] > 0:
        quick_recommendations.append(
            "Distribuir el disponible entre meta crítica, deuda e imprevistos."
        )

    dashboard_cards = [
        {
            "title": "Ingreso mensual neto",
            "value": income["monthly_net_income"],
            "type": "currency",
            "status": "info"
        },
        {
            "title": "Disponible estimado",
            "value": cashflow["available_cash"],
            "type": "currency",
            "status": "warning" if cashflow["available_cash"] < 100000 else "good"
        },
        {
            "title": "Gastos fijos",
            "value": expenses["fixed_expenses"],
            "type": "currency",
            "status": "info"
        },
        {
            "title": "Deuda total",
            "value": debts["total"],
            "type": "currency",
            "status": "danger"
        },
        {
            "title": "Patrimonio neto",
            "value": user_status["assets"]["net_worth"],
            "type": "currency",
            "status": "danger" if user_status["assets"]["net_worth"] < 0 else "good"
        },
        {
            "title": "Meta principal",
            "value": (
                goals["most_urgent_goal"]["name"]
                if goals["most_urgent_goal"]
                else "Sin meta activa"
            ),
            "type": "text",
            "status": "warning" if goals["most_urgent_goal"] else "good"
        }
    ]

    top_debts = net_worth["liabilities"]["debts"][:3]

    return {
        "cards": dashboard_cards,
        "alerts": alerts,
        "quick_recommendations": quick_recommendations,
        "top_debts": top_debts,
        "summary": {
            "income": income,
            "expenses": expenses,
            "cashflow": cashflow,
            "debts": debts,
            "assets": user_status["assets"],
            "goals": goals,
            "financial_health": financial_health
        }
    }