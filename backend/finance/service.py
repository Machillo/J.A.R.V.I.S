from backend.core.database import get_connection


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
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                name,
                debt_type,
                total_amount,
                remaining_amount,
                monthly_payment,
                interest_rate,
                term_months,
                payment_day
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
        "payment_day": payment_day
    }


def get_debts():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount, monthly_payment,
                   interest_rate, term_months, payment_day, created_at
            FROM debts
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def add_saving(name: str, amount: float):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO savings (name, amount, created_at)
            VALUES (?, ?, datetime('now'))
            """,
            (name, amount)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "amount": amount
    }


def get_savings():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, amount, created_at
            FROM savings
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def add_investment(name: str, amount: float):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO investments (name, amount, created_at)
            VALUES (?, ?, datetime('now'))
            """,
            (name, amount)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "amount": amount
    }


def get_investments():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, amount, created_at
            FROM investments
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def add_expense(
    category: str,
    amount: float,
    expense_type: str = "variable",
    description: str = ""
):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO expenses (category, expense_type, description, amount, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (category, expense_type, description, amount)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "category": category,
        "expense_type": expense_type,
        "description": description,
        "amount": amount
    }


def get_expenses():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, category, expense_type, description, amount, created_at
            FROM expenses
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_financial_summary():
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
            "SELECT COALESCE(SUM(amount), 0) AS total FROM bonuses"
        ).fetchone()["total"]

        debt_total = conn.execute(
            "SELECT COALESCE(SUM(remaining_amount), 0) AS total FROM debts"
        ).fetchone()["total"]

        monthly_debt_payments = conn.execute(
            "SELECT COALESCE(SUM(monthly_payment), 0) AS total FROM debts"
        ).fetchone()["total"]

        savings_total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM savings"
        ).fetchone()["total"]

        investments_total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM investments"
        ).fetchone()["total"]

        fixed_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'fixed'
            """
        ).fetchone()["total"]

        variable_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'variable'
            """
        ).fetchone()["total"]

        one_time_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'one_time'
            """
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
        }
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
    with get_connection() as conn:
        expense = conn.execute(
            """
            SELECT id, category, expense_type, amount, description
            FROM expenses
            WHERE id = ?
            """,
            (expense_id,)
        ).fetchone()

        if not expense:
            return {
                "message": "Gasto no encontrado.",
                "status": "ERROR"
            }

        conn.execute(
            """
            DELETE FROM expenses
            WHERE id = ?
            """,
            (expense_id,)
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
    with get_connection() as conn:
        expense = conn.execute(
            """
            SELECT id
            FROM expenses
            WHERE id = ?
            """,
            (expense_id,)
        ).fetchone()

        if not expense:
            return {
                "message": "Gasto no encontrado.",
                "status": "ERROR"
            }

        conn.execute(
            """
            UPDATE expenses
            SET category = ?, amount = ?, expense_type = ?, description = ?
            WHERE id = ?
            """,
            (category, amount, expense_type, description, expense_id)
        )

        conn.commit()

    return {
        "message": "Gasto actualizado correctamente.",
        "id": expense_id,
        "category": category,
        "amount": amount,
        "expense_type": expense_type,
        "description": description,
        "status": "OK"
    }

def delete_debt(debt_id: int):
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

        conn.execute("DELETE FROM debt_payments WHERE debt_id = ?", (debt_id,))
        conn.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
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
    with get_connection() as conn:
        debt = conn.execute(
            "SELECT id FROM debts WHERE id = ?",
            (debt_id,)
        ).fetchone()

        if not debt:
            return {
                "message": "Deuda no encontrada.",
                "status": "ERROR"
            }

        conn.execute(
            """
            UPDATE debts
            SET name = ?, debt_type = ?, total_amount = ?, remaining_amount = ?,
                monthly_payment = ?, interest_rate = ?, term_months = ?, payment_day = ?
            WHERE id = ?
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
                debt_id
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
    search = f"%{name.lower()}%"

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, name, total_amount, remaining_amount, monthly_payment, interest_rate, created_at
            FROM debts
            WHERE lower(name) LIKE ?
            LIMIT 1
            """,
            (search,)
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