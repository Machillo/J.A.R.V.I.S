from datetime import date, datetime, timedelta
from typing import Any

from backend.core.database import get_connection
from backend.auth.current_user import get_current_user_id
from backend.finance.category_catalog import normalize_category, expense_type_for_category


def _as_float(value, default: float = 0.0) -> float:
    """Convierte valores de PostgreSQL NUMERIC/None a float seguro."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_sum(items: list[dict], key: str) -> float:
    return sum(_as_float(item.get(key)) for item in items)


def _current_month_bounds_sql() -> tuple[str, str]:
    today = date.today()
    start = today.replace(day=1).isoformat()
    if today.month == 12:
        end = date(today.year + 1, 1, 1).isoformat()
    else:
        end = date(today.year, today.month + 1, 1).isoformat()
    return start, end


def _financial_cycle_bounds(today: date | None = None, closing_day: int = 5) -> tuple[date, date]:
    """Kenneth's operating cycle is 5 -> 5, not calendar month.

    The end date is exclusive. Example: Jun 5 <= date < Jul 5.
    """
    today = today or date.today()
    if today.day >= closing_day:
        start = today.replace(day=closing_day)
        if today.month == 12:
            end = date(today.year + 1, 1, closing_day)
        else:
            end = date(today.year, today.month + 1, closing_day)
    else:
        end = today.replace(day=closing_day)
        if today.month == 1:
            start = date(today.year - 1, 12, closing_day)
        else:
            start = date(today.year, today.month - 1, closing_day)
    return start, end



def _card_billing_cycle_bounds(today: date | None = None, cut_day: int = 21) -> tuple[date, date]:
    """BAC card expense cycle: 21 -> 21, end exclusive.

    Kenneth reviews card spending by statement cut, not by the operating cash
    cycle used for payroll/card payment planning. Example on Jun 10: May 21 <=
    expense_date < Jun 21.
    """
    today = today or date.today()
    if today.day >= cut_day:
        start = today.replace(day=cut_day)
        if today.month == 12:
            end = date(today.year + 1, 1, cut_day)
        else:
            end = date(today.year, today.month + 1, cut_day)
    else:
        end = today.replace(day=cut_day)
        if today.month == 1:
            start = date(today.year - 1, 12, cut_day)
        else:
            start = date(today.year, today.month - 1, cut_day)
    return start, end

def _next_thursday_after_work_week(value: Any) -> date | None:
    """Estimate payroll date for OT/VGH/holiday/vacation events.

    Work events are paid the following Thursday. This keeps OT out of the current
    cycle when the Thursday payment falls after the card payment cut (5th).
    """
    if not value:
        return None
    if isinstance(value, datetime):
        event_date = value.date()
    elif isinstance(value, date):
        event_date = value
    else:
        raw = str(value)
        try:
            event_date = datetime.fromisoformat(raw.replace('Z', '+00:00')).date()
        except ValueError:
            try:
                event_date = datetime.strptime(raw[:10], '%Y-%m-%d').date()
            except ValueError:
                return None

    # Move at least one week forward, then find Thursday. Monday=0, Thursday=3.
    base = event_date + timedelta(days=7)
    days_until_thursday = (3 - base.weekday()) % 7
    return base + timedelta(days=days_until_thursday)


def _transaction_date_expr() -> str:
    """Safe SQL expression that converts transactions.transaction_date to DATE.

    Older deployments may have transaction_date as TEXT, while newer/imported
    tables may expose it as DATE. Casting to text first avoids PostgreSQL trying
    to cast the empty-string literal to DATE inside NULLIF. The regex guard also
    prevents invalid legacy values from crashing /finance/cycle-report.
    """
    raw = "NULLIF(BTRIM(transaction_date::text), '')"
    return (
        "CASE "
        f"WHEN {raw} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' "
        f"THEN SUBSTRING({raw} FROM 1 FOR 10)::date "
        "ELSE NULL END"
    )


def _latest_base_salary(user_id: int) -> float:
    """Base mensual fija. Preferimos un salario base guardado; no depende de que entren transacciones bancarias."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT amount, source
            FROM salaries
            WHERE user_id = %s
            ORDER BY
                CASE
                    WHEN LOWER(source) LIKE '%%base%%' THEN 0
                    WHEN LOWER(source) LIKE '%%mensual%%' THEN 1
                    ELSE 2
                END,
                id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    return _as_float(row["amount"] if row else 0)


def _normalize_debt_payment_value(value: float, remaining_amount: float = 0) -> float:
    """Corrige montos importados sin decimales: 6547840 => 65478.40.

    Nunca deja que una cuota mensual sea mayor que el saldo total salvo que realmente sea
    un cierre de deuda pequeño. Esto evita que la estrategia muestre pagos mínimos absurdos.
    """
    value = _as_float(value)
    remaining_amount = _as_float(remaining_amount)
    if value <= 0:
        return 0.0
    if remaining_amount > 0 and value > remaining_amount and value >= 100000:
        scaled = value / 100
        if scaled <= max(remaining_amount, 1_000_000):
            return round(scaled, 2)
    if value >= 1_000_000:
        return round(value / 100, 2)
    return round(value, 2)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day


def _month_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(max(int(day or 1), 1), _days_in_month(year, month)))


def _add_months(value: date, months: int, day: int | None = None) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    return _month_date(year, month, day or value.day)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00')).date()
    except ValueError:
        try:
            return datetime.strptime(raw[:10], '%Y-%m-%d').date()
        except ValueError:
            return None


def _default_first_payment_date(created_at: Any, payment_day: int | None) -> date:
    created = _parse_date(created_at) or date.today()
    day = int(payment_day or created.day)
    candidate = _month_date(created.year, created.month, day)
    if candidate < created:
        candidate = _add_months(candidate, 1, day)
    return candidate


def _count_due_installments(first_due: date, as_of: date, payment_day: int, term_months: int | None) -> int:
    """Cantidad de cuotas cuyo vencimiento ya ocurrió, incluida la fecha actual."""
    count = 0
    due = first_due
    limit = int(term_months or 0)
    while due <= as_of and (limit <= 0 or count < limit):
        count += 1
        due = _add_months(first_due, count, payment_day)
    return count


def _estimate_installments(total_amount: float, monthly_payment: float, annual_rate: float = 0) -> int | None:
    total = max(_as_float(total_amount), 0)
    payment = max(_as_float(monthly_payment), 0)
    if total <= 0 or payment <= 0:
        return None
    monthly_rate = max(_as_float(annual_rate), 0) / 100 / 12
    if monthly_rate <= 0:
        return max(int((total + payment - 0.01) // payment), 1)
    if payment <= total * monthly_rate:
        return None
    import math
    months = -math.log(1 - (monthly_rate * total / payment)) / math.log(1 + monthly_rate)
    return max(int(math.ceil(months)), 1)


def _estimate_paid_installments(total_amount: float, remaining_amount: float, monthly_payment: float, annual_rate: float = 0, term_months: int | None = None) -> int:
    total_term = int(term_months or 0) or _estimate_installments(total_amount, monthly_payment, annual_rate)
    remaining_term = _estimate_installments(remaining_amount, monthly_payment, annual_rate)
    if not total_term or remaining_term is None:
        principal_paid = max(_as_float(total_amount) - _as_float(remaining_amount), 0)
        return max(int(principal_paid // max(_as_float(monthly_payment), 1)), 0)
    return max(min(total_term - remaining_term, total_term), 0)


def _scheduled_payment_breakdown(balance: float, payment: float, annual_rate: float) -> tuple[float, float, float]:
    balance = max(_as_float(balance), 0)
    payment = min(max(_as_float(payment), 0), balance + max(balance * max(_as_float(annual_rate), 0) / 100 / 12, 0))
    interest = round(balance * max(_as_float(annual_rate), 0) / 100 / 12, 2)
    principal = round(max(payment - interest, 0), 2)
    if principal > balance:
        principal = balance
        payment = round(principal + interest, 2)
    return round(payment, 2), round(principal, 2), round(interest, 2)


def _sync_automatic_debt_payments(user_id: int) -> None:
    """Sincroniza cuotas vencidas usando fechas reales y un libro de pagos idempotente.

    La fecha de inicio, primera cuota, día de pago y fecha actual determinan cuántas
    cuotas debieron aplicarse. Cada cuota se registra una sola vez en debt_payments.
    """
    today = date.today()
    with get_connection() as conn:
        debts = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount, monthly_payment,
                   interest_rate, term_months, payment_day, start_date, first_payment_date,
                   auto_update_monthly, installments_paid, created_at
            FROM debts
            WHERE user_id = %s
              AND COALESCE(auto_update_monthly, TRUE) = TRUE
              AND remaining_amount > 0
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()

        changed = False
        for debt in debts:
            payment_day = int(debt.get("payment_day") or 1)
            start_date = _parse_date(debt.get("start_date")) or _parse_date(debt.get("created_at")) or today
            first_due = _parse_date(debt.get("first_payment_date")) or _default_first_payment_date(start_date, payment_day)
            term = int(debt.get("term_months") or 0) or _estimate_installments(
                debt.get("total_amount"), debt.get("monthly_payment"), debt.get("interest_rate")
            )
            target_paid = _count_due_installments(first_due, today, payment_day, term)

            payment_rows = conn.execute(
                """
                SELECT payment_date, installment_number
                FROM debt_payments
                WHERE user_id = %s AND debt_id = %s AND payment_type = 'monthly_payment'
                ORDER BY installment_number, payment_date
                """,
                (user_id, debt["id"]),
            ).fetchall()
            existing_dates = {str(row.get("payment_date"))[:10] for row in payment_rows if row.get("payment_date")}
            ledger_paid = max([int(row.get("installment_number") or 0) for row in payment_rows] or [0])
            paid_count = max(int(debt.get("installments_paid") or 0), ledger_paid)
            balance = _as_float(debt.get("remaining_amount"))
            monthly_payment = _normalize_debt_payment_value(debt.get("monthly_payment"), balance)
            if monthly_payment <= 0:
                continue

            # El valor histórico guardado actúa como ancla; solo creamos cuotas posteriores.
            for installment_number in range(paid_count + 1, target_paid + 1):
                due = _add_months(first_due, installment_number - 1, payment_day)
                if due.isoformat() in existing_dates:
                    paid_count = max(paid_count, installment_number)
                    continue

                previous_balance = balance
                actual_payment, principal, interest = _scheduled_payment_breakdown(
                    balance, monthly_payment, debt.get("interest_rate")
                )
                if principal <= 0:
                    break
                balance = round(max(balance - principal, 0), 2)

                conn.execute(
                    """
                    INSERT INTO debt_payments (
                        user_id, debt_id, payment_type, amount, principal_amount, interest_amount,
                        previous_remaining_amount, new_remaining_amount,
                        previous_monthly_payment, new_monthly_payment, description,
                        payment_date, installment_number, source, created_at
                    )
                    SELECT %s, %s, 'monthly_payment', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'auto_schedule', NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM debt_payments
                        WHERE user_id = %s AND debt_id = %s
                          AND payment_type = 'monthly_payment' AND payment_date = %s
                    )
                    """,
                    (
                        user_id, debt["id"], actual_payment, principal, interest, previous_balance, balance,
                        monthly_payment, monthly_payment,
                        f"Cuota automática {installment_number}/{term or '?'} de {debt.get('name') or 'deuda'}",
                        due.isoformat(), installment_number,
                        user_id, debt["id"], due.isoformat(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO transactions (
                        user_id, transaction_date, description, amount, transaction_type,
                        category, account, source, notes, created_at
                    )
                    SELECT %s, %s, %s, %s, 'debt_payment', %s, NULL, 'auto_debt_schedule', %s, NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM transactions
                        WHERE user_id = %s AND source = 'auto_debt_schedule' AND notes = %s
                    )
                    """,
                    (
                        user_id, due.isoformat(), f"Cuota {debt.get('name') or 'deuda'}", actual_payment,
                        debt.get("name") or "Deudas", f"debt_id:{debt['id']};installment:{installment_number}",
                        user_id, f"debt_id:{debt['id']};installment:{installment_number}",
                    ),
                )
                paid_count = installment_number
                existing_dates.add(due.isoformat())
                changed = True

            # Siempre normalizamos las fechas y el contador, aunque no haya una cuota nueva.
            conn.execute(
                """
                UPDATE debts
                SET start_date = COALESCE(start_date, %s),
                    first_payment_date = COALESCE(first_payment_date, %s),
                    remaining_amount = %s,
                    installments_paid = %s,
                    updated_at = CASE WHEN remaining_amount <> %s OR installments_paid <> %s THEN NOW() ELSE updated_at END
                WHERE id = %s AND user_id = %s
                """,
                (
                    start_date.isoformat(), first_due.isoformat(), balance, paid_count,
                    balance, paid_count, debt["id"], user_id,
                ),
            )

        conn.commit()

def _monthly_amount_from_frequency(amount: float, frequency: str | None) -> float:
    frequency = (frequency or 'monthly').lower().strip()
    amount = _as_float(amount)
    if frequency == 'weekly':
        return amount * 4.333
    if frequency in {'biweekly', 'cada_2_semanas', 'quincenal'}:
        return amount * 2.166
    if frequency == 'annual':
        return amount / 12
    return amount


def _variable_payroll_deductions(gross_amount: float, deductions: list[dict]) -> tuple[float, list[dict]]:
    """Rebajos aplicables a OT/bonos/VGH.

    Si el salario base mensual ya está guardado como neto, no repetimos rebajos fijos
    semanales sobre el salario base. Para ingresos extra aplicamos solo rebajos
    porcentuales configurados.
    """
    total = 0.0
    details = []
    for deduction in deductions:
        deduction_type = str(deduction.get('deduction_type') or '').lower().strip()
        amount = _as_float(deduction.get('amount'))
        if deduction_type == 'percentage':
            calculated = gross_amount * (amount / 100)
            total += calculated
            details.append({
                'name': deduction.get('name'),
                'deduction_type': deduction_type,
                'base_amount': amount,
                'frequency': deduction.get('frequency'),
                'calculated_monthly_amount': calculated,
                'applies_to': 'extra_income',
            })
    return total, details


def add_salary(amount: float, source: str):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO salaries (amount, source, user_id, created_at)
            VALUES (%s, %s, %s, NOW())
            """,
            (amount, source, user_id)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "amount": amount,
        "source": source,
        "user_id": user_id
    }


def get_salaries():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, source, user_id, created_at
            FROM salaries
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def add_bonus(amount: float, description: str = ""):
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bonuses (amount, description, user_id, created_at)
            VALUES (%s, %s, %s, NOW())
            """,
            (amount, description, user_id)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "amount": amount,
        "description": description,
        "user_id": user_id
    }


def get_bonuses():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, description, user_id, created_at
            FROM bonuses
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
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
    payment_day: int | None = None,
    start_date: str | None = None,
    first_payment_date: str | None = None,
    installments_paid: int = 0,
    auto_update_monthly: bool = True,
):
    user_id = get_current_user_id()
    normalized_start = _parse_date(start_date) or date.today()
    normalized_first = _parse_date(first_payment_date) or _default_first_payment_date(normalized_start, payment_day)

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
                start_date,
                first_payment_date,
                auto_update_monthly,
                installments_paid,
                user_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id
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
                normalized_start.isoformat(),
                normalized_first.isoformat(),
                auto_update_monthly,
                max(int(installments_paid or 0), 0),
                user_id
            )
        )
        inserted = cursor.fetchone()
        inserted_id = inserted["id"] if inserted else None

        conn.commit()

    return {
        "id": inserted_id,
        "name": name,
        "debt_type": debt_type,
        "total_amount": total_amount,
        "remaining_amount": remaining_amount,
        "monthly_payment": monthly_payment,
        "interest_rate": interest_rate,
        "term_months": term_months,
        "payment_day": payment_day,
        "start_date": normalized_start.isoformat(),
        "first_payment_date": normalized_first.isoformat(),
        "installments_paid": max(int(installments_paid or 0), 0),
        "auto_update_monthly": auto_update_monthly,
        "user_id": user_id
    }


def get_debts():
    user_id = get_current_user_id()
    _sync_automatic_debt_payments(user_id)

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
                   start_date,
                   first_payment_date,
                   auto_update_monthly,
                   installments_paid,
                   updated_at,
                   created_at,
                   user_id
            FROM debts
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    debts = [dict(row) for row in rows]
    with get_connection() as conn:
        payment_stats = conn.execute(
            """
            SELECT debt_id,
                   COUNT(*) FILTER (WHERE payment_type = 'monthly_payment') AS monthly_count,
                   MAX(installment_number) FILTER (WHERE payment_type = 'monthly_payment') AS max_installment,
                   MAX(payment_date) FILTER (WHERE payment_type = 'monthly_payment') AS last_payment_date
            FROM debt_payments
            WHERE user_id = %s
            GROUP BY debt_id
            """,
            (user_id,),
        ).fetchall()
    stats_by_debt = {int(row["debt_id"]): dict(row) for row in payment_stats}
    today = date.today()
    for debt in debts:
        debt["monthly_payment_raw"] = debt.get("monthly_payment")
        debt["monthly_payment"] = _normalize_debt_payment_value(
            debt.get("monthly_payment"),
            debt.get("remaining_amount"),
        )
        total_installments = int(debt.get("term_months") or 0) or _estimate_installments(
            debt.get("total_amount"), debt.get("monthly_payment"), debt.get("interest_rate")
        )
        stat = stats_by_debt.get(int(debt["id"]), {})
        paid_installments = max(
            int(debt.get("installments_paid") or 0),
            int(stat.get("max_installment") or stat.get("monthly_count") or 0),
        )
        if total_installments:
            paid_installments = min(paid_installments, total_installments)
        start = _parse_date(debt.get("start_date")) or _parse_date(debt.get("created_at")) or today
        first_due = _parse_date(debt.get("first_payment_date")) or _default_first_payment_date(start, debt.get("payment_day"))
        next_due = (
            _add_months(first_due, paid_installments, debt.get("payment_day") or first_due.day)
            if _as_float(debt.get("remaining_amount")) > 0 and (not total_installments or paid_installments < total_installments)
            else None
        )
        debt["start_date"] = start.isoformat()
        debt["registered_date"] = (_parse_date(debt.get("created_at")) or start).isoformat()
        debt["current_date"] = today.isoformat()
        debt["first_payment_date"] = first_due.isoformat()
        debt["last_payment_date"] = str(stat.get("last_payment_date"))[:10] if stat.get("last_payment_date") else None
        debt["next_payment_date"] = next_due.isoformat() if next_due else None
        debt["total_installments"] = total_installments
        debt["paid_installments"] = paid_installments
        debt["remaining_installments"] = max(total_installments - paid_installments, 0) if total_installments else None
        debt["progress_percent"] = round((paid_installments / total_installments) * 100, 2) if total_installments else 0
        debt["schedule_status"] = "paid" if _as_float(debt.get("remaining_amount")) <= 0 else ("current" if not next_due or next_due > today else "due")
    return debts


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
            VALUES (%s, %s, %s, NOW())
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
            WHERE user_id = %s
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
            WHERE id = %s
            AND user_id = %s
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
            SET name = %s,
                amount = %s
            WHERE id = %s
            AND user_id = %s
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
            WHERE id = %s
            AND user_id = %s
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
            WHERE id = %s
            AND user_id = %s
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
            VALUES (%s, %s, %s, NOW())
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
            WHERE user_id = %s
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
            WHERE id = %s
            AND user_id = %s
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
            SET name = %s,
                amount = %s
            WHERE id = %s
            AND user_id = %s
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
            WHERE id = %s
            AND user_id = %s
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
            WHERE id = %s
            AND user_id = %s
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
    category = normalize_category(category, "expense")
    if not expense_type or expense_type == "variable":
        expense_type = expense_type_for_category(category)

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
            VALUES (%s, %s, %s, %s, %s, NOW())
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
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_financial_summary():
    """
    Resumen financiero tolerante a base vacía.
    Si el usuario aún no configuró perfil laboral, ingresos, gastos o deudas,
    devuelve ceros en vez de romper el dashboard.
    """
    user_id = get_current_user_id()

    salary_projection = calculate_monthly_salary_projection()

    if salary_projection.get("status") == "ERROR":
        projected_net_income = 0.0
        projected_gross_income = 0.0
        payroll_deductions_total = 0.0
    else:
        projected_net_income = _as_float(
            salary_projection.get("results", {}).get("projected_net")
        )
        projected_gross_income = _as_float(
            salary_projection.get("adjustments", {}).get("projected_gross")
        )
        payroll_deductions_total = _as_float(
            salary_projection.get("deductions", {}).get("total_deductions")
        )

    with get_connection() as conn:
        bonus_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM bonuses
            WHERE user_id = %s
            """,
            (user_id,)
        ).fetchone()["total"]

        debt_total = conn.execute(
            """
            SELECT COALESCE(SUM(remaining_amount), 0) AS total
            FROM debts
            WHERE user_id = %s
            """,
            (user_id,)
        ).fetchone()["total"]

        monthly_debt_payments = conn.execute(
            """
            SELECT COALESCE(SUM(monthly_payment), 0) AS total
            FROM debts
            WHERE user_id = %s
            """,
            (user_id,)
        ).fetchone()["total"]

        savings_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM savings
            WHERE user_id = %s
            """,
            (user_id,)
        ).fetchone()["total"]

        investments_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM investments
            WHERE user_id = %s
            """,
            (user_id,)
        ).fetchone()["total"]

        legacy_fixed_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'fixed'
            AND user_id = %s
            """,
            (user_id,)
        ).fetchone()["total"]

        fixed_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(
                CASE
                    WHEN frequency = 'weekly' THEN expected_amount * 4.333
                    WHEN frequency IN ('biweekly', 'quincenal') THEN expected_amount * 2.166
                    WHEN frequency = 'bimonthly' THEN expected_amount / 2
                    WHEN frequency = 'annual' THEN expected_amount / 12
                    ELSE expected_amount
                END
            ), 0) AS total
            FROM fixed_expenses
            WHERE user_id = %s
              AND is_active = TRUE
              AND expected_amount IS NOT NULL
            """,
            (user_id,)
        ).fetchone()["total"]

        variable_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'variable'
            AND user_id = %s
            """,
            (user_id,)
        ).fetchone()["total"]

        one_time_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'one_time'
            AND user_id = %s
            """,
            (user_id,)
        ).fetchone()["total"]

    bonus_total = _as_float(salary_projection.get("adjustments", {}).get("bonuses_net", bonus_total))
    debt_total = _as_float(debt_total)
    # Normaliza cuotas absurdas importadas sin punto decimal.
    debts_for_minimums = get_debts()
    monthly_debt_payments = sum(_normalize_debt_payment_value(d.get("monthly_payment"), d.get("remaining_amount")) for d in debts_for_minimums)
    savings_total = _as_float(savings_total)
    investments_total = _as_float(investments_total)
    legacy_fixed_expenses_total = _as_float(locals().get("legacy_fixed_expenses_total", 0))
    fixed_expenses_total = max(_as_float(fixed_expenses_total), legacy_fixed_expenses_total)
    variable_expenses_total = _as_float(variable_expenses_total)
    one_time_expenses_total = _as_float(one_time_expenses_total)

    # projected_net_income ya incluye salario base + OT/VGH + bonos del mes.
    total_income = projected_net_income
    expenses_total = fixed_expenses_total + variable_expenses_total + one_time_expenses_total
    available_cash = total_income - monthly_debt_payments - expenses_total
    net_worth = savings_total + investments_total - debt_total

    return {
        "income": {
            "projected_gross_income": projected_gross_income,
            "payroll_deductions_total": payroll_deductions_total,
            "projected_net_income": projected_net_income,
            "bonus_total": bonus_total,
            "total_income": total_income,
            "is_configured": projected_net_income > 0 or projected_gross_income > 0,
        },
        "debts": {
            "debt_total": debt_total,
            "monthly_debt_payments": monthly_debt_payments,
        },
        "assets": {
            "savings_total": savings_total,
            "investments_total": investments_total,
        },
        "expenses": {
            "fixed_expenses_total": fixed_expenses_total,
            "variable_expenses_total": variable_expenses_total,
            "one_time_expenses_total": one_time_expenses_total,
            "expenses_total": expenses_total,
        },
        "results": {
            "available_cash": available_cash,
            "net_worth": net_worth,
        },
        "setup": {
            "has_income_profile": projected_net_income > 0 or projected_gross_income > 0,
            "has_financial_data": any([
                bonus_total,
                debt_total,
                savings_total,
                investments_total,
                expenses_total,
            ]),
        },
        "user_id": user_id,
    }

def get_financial_cycle_report() -> dict:
    """Finance dashboard report for the real 5->5 cycle.

    Rules:
    - Fixed expected income is the known base payroll projection.
    - Extras include OT, bonus, VGH, holiday and vacation only when their
      estimated/recorded payment date lands inside the current 5->5 cycle.
    - Expenses and debt payments come from accepted real transactions in the
      current cycle.
    """
    user_id = get_current_user_id()
    cycle_start, cycle_end = _financial_cycle_bounds()
    expense_cycle_start, expense_cycle_end = _card_billing_cycle_bounds()
    query_start = min(cycle_start, expense_cycle_start)
    query_end = max(cycle_end, expense_cycle_end)
    salary_projection = calculate_monthly_salary_projection()

    base_net = _as_float(salary_projection.get("results", {}).get("base_net"))
    deduction_details = salary_projection.get("deductions", {}) or {}

    with get_connection() as conn:
        payroll_events = [dict(row) for row in conn.execute(
            """
            SELECT id, event_type, hours, multiplier, amount, description, created_at
            FROM payroll_events
            WHERE user_id = %s
            ORDER BY created_at ASC
            """,
            (user_id,),
        ).fetchall()]

        bonuses = [dict(row) for row in conn.execute(
            """
            SELECT id, amount, description, created_at
            FROM bonuses
            WHERE user_id = %s
            ORDER BY created_at ASC
            """,
            (user_id,),
        ).fetchall()]

        transaction_rows = [dict(row) for row in conn.execute(
            f"""
            SELECT id, transaction_date, description, amount, transaction_type,
                   category, account, source, notes, created_at
            FROM transactions
            WHERE user_id = %s
              AND {_transaction_date_expr()} >= %s::date
              AND {_transaction_date_expr()} < %s::date
            ORDER BY {_transaction_date_expr()} DESC, id DESC
            """,
            (user_id, query_start.isoformat(), query_end.isoformat()),
        ).fetchall()]

    deductions_total = _as_float(deduction_details.get("extra_deductions_total"))
    positive_events_total = sum(max(_as_float(event.get("amount")), 0) for event in payroll_events)
    bonus_total_all = sum(max(_as_float(item.get("amount")), 0) for item in bonuses)
    extra_gross_base = positive_events_total + bonus_total_all

    extra_items: list[dict] = []
    extra_expected = 0.0
    for event in payroll_events:
        pay_date = _next_thursday_after_work_week(event.get("created_at"))
        if not pay_date or not (cycle_start <= pay_date < cycle_end):
            continue
        gross = _as_float(event.get("amount"))
        proportional_deduction = 0.0
        if gross > 0 and extra_gross_base > 0:
            proportional_deduction = deductions_total * (gross / extra_gross_base)
        net = gross - proportional_deduction if gross > 0 else gross
        extra_expected += net
        extra_items.append({
            **event,
            "kind": "payroll_event",
            "estimated_pay_date": pay_date.isoformat(),
            "gross_amount": round(gross, 2),
            "net_amount": round(net, 2),
        })

    for bonus in bonuses:
        created = bonus.get("created_at")
        if isinstance(created, datetime):
            pay_date = created.date()
        else:
            try:
                pay_date = datetime.fromisoformat(str(created).replace('Z', '+00:00')).date()
            except Exception:
                pay_date = None
        if not pay_date or not (cycle_start <= pay_date < cycle_end):
            continue
        gross = _as_float(bonus.get("amount"))
        proportional_deduction = 0.0
        if gross > 0 and extra_gross_base > 0:
            proportional_deduction = deductions_total * (gross / extra_gross_base)
        net = gross - proportional_deduction
        extra_expected += net
        extra_items.append({
            **bonus,
            "kind": "bonus",
            "estimated_pay_date": pay_date.isoformat(),
            "gross_amount": round(gross, 2),
            "net_amount": round(net, 2),
        })

    def _row_date(row: dict) -> date | None:
        raw = row.get("transaction_date")
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        try:
            return datetime.fromisoformat(str(raw)[:10]).date()
        except Exception:
            return None

    def _inside(row: dict, start: date, end: date) -> bool:
        row_date = _row_date(row)
        return bool(row_date and start <= row_date < end)

    expenses = [
        row for row in transaction_rows
        if row.get("transaction_type") == "expense"
        and _inside(row, expense_cycle_start, expense_cycle_end)
    ]
    debt_payments = [
        row for row in transaction_rows
        if row.get("transaction_type") == "debt_payment"
        and _inside(row, cycle_start, cycle_end)
    ]
    income_transactions = [
        row for row in transaction_rows
        if row.get("transaction_type") == "income"
        and _inside(row, cycle_start, cycle_end)
    ]
    loan_transactions = [
        row for row in transaction_rows
        if row.get("transaction_type") in {"loan_received", "loan_disbursement"}
        and _inside(row, cycle_start, cycle_end)
    ]

    expenses_total = sum(_as_float(row.get("amount")) for row in expenses)
    debt_payments_total = sum(_as_float(row.get("amount")) for row in debt_payments)
    income_received_total = sum(_as_float(row.get("amount")) for row in income_transactions)
    loans_total = sum(_as_float(row.get("amount")) for row in loan_transactions)
    expected_total = base_net + extra_expected
    try:
        from backend.finance.intelligence import calculate_goal_reserves, _fetch_active_goals
        goal_reserves = calculate_goal_reserves(_fetch_active_goals(user_id))
    except Exception:
        goal_reserves = {
            "items": [],
            "monthly_required_all_goals": 0,
            "monthly_auto_reserve": 0,
            "critical_monthly_required": 0,
        }

    goals_reserved = max(
        _as_float(goal_reserves.get("critical_monthly_required")),
        _as_float(goal_reserves.get("monthly_auto_reserve")),
    )
    real_balance = expected_total + income_received_total + loans_total - expenses_total - debt_payments_total - goals_reserved

    return {
        "status": "OK",
        "cycle": {
            "start": cycle_start.isoformat(),
            "end": cycle_end.isoformat(),
            "label": f"{cycle_start.isoformat()} → {cycle_end.isoformat()}",
            "closing_day": 5,
        },
        "expense_cycle": {
            "start": expense_cycle_start.isoformat(),
            "end": expense_cycle_end.isoformat(),
            "label": f"{expense_cycle_start.isoformat()} → {expense_cycle_end.isoformat()}",
            "cut_day": 21,
        },
        "income": {
            "fixed_expected": round(base_net, 2),
            "extra_expected": round(extra_expected, 2),
            "expected_total": round(expected_total, 2),
            "received_from_transactions": round(income_received_total, 2),
            "items": extra_items,
        },
        "expenses": {
            "current_period": round(expenses_total, 2),
            "items": expenses,
        },
        "debts": {
            "payments_current_period": round(debt_payments_total, 2),
            "items": debt_payments,
        },
        "goals": {
            "reserved_current_period": round(goals_reserved, 2),
            "reserves": goal_reserves,
        },
        "cashflow": {
            "real_balance": round(real_balance, 2),
            "loan_received": round(loans_total, 2),
            "formula": "Ingreso Neto - Gastos Fijos/Variables - Deudas - Metas Críticas",
        },
        "transactions": expenses + debt_payments + income_transactions + loan_transactions,
        "payroll_projection": salary_projection,
        "user_id": user_id,
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
    user_id = get_current_user_id()

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM employment_profile WHERE user_id = %s",
            (user_id,)
        )

        cursor = conn.execute(
            """
            INSERT INTO employment_profile (
                hourly_rate,
                regular_hours_per_week,
                overtime_multiplier,
                holiday_multiplier,
                user_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (
                hourly_rate,
                regular_hours_per_week,
                overtime_multiplier,
                holiday_multiplier,
                user_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "hourly_rate": hourly_rate,
        "regular_hours_per_week": regular_hours_per_week,
        "overtime_multiplier": overtime_multiplier,
        "holiday_multiplier": holiday_multiplier,
        "user_id": user_id
    }


def get_employment_profile():
    user_id = get_current_user_id()

    with get_connection() as conn:
        profile = conn.execute(
            """
            SELECT id, hourly_rate, regular_hours_per_week, overtime_multiplier, holiday_multiplier, user_id, created_at
            FROM employment_profile
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
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
    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO payroll_deductions (
                name,
                deduction_type,
                amount,
                frequency,
                user_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (name, deduction_type, amount, frequency, user_id)
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "deduction_type": deduction_type,
        "amount": amount,
        "frequency": frequency,
        "user_id": user_id
    }


def get_payroll_deductions():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, deduction_type, amount, frequency, user_id, created_at
            FROM payroll_deductions
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
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

    user_id = get_current_user_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO payroll_events (
                event_type,
                hours,
                multiplier,
                amount,
                description,
                user_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                event_type,
                hours,
                multiplier,
                amount,
                description,
                user_id
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
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, event_type, hours, multiplier, amount, description, user_id, created_at
            FROM payroll_events
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def calculate_monthly_salary_projection():
    """Proyección mensual real de planilla.

    Reglas V1:
    - El salario base mensual es fijo y no depende de movimientos bancarios.
    - OT y bonos se suman solo en el mes actual.
    - VGH resta salario del mes actual.
    - Los rebajos porcentuales configurados se aplican a OT/bonos; los rebajos fijos
      semanales se usan únicamente si no hay salario base neto guardado.
    """
    user_id = get_current_user_id()
    profile = get_employment_profile()
    start_month, end_month = _current_month_bounds_sql()

    with get_connection() as conn:
        deductions = [dict(row) for row in conn.execute(
            """
            SELECT name, deduction_type, amount, frequency
            FROM payroll_deductions
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()]

        payroll_events = [dict(row) for row in conn.execute(
            """
            SELECT event_type, hours, multiplier, amount, description, created_at
            FROM payroll_events
            WHERE user_id = %s
              AND created_at >= %s::date
              AND created_at < %s::date
            ORDER BY created_at ASC
            """,
            (user_id, start_month, end_month),
        ).fetchall()]

        current_bonuses = [dict(row) for row in conn.execute(
            """
            SELECT amount, description, created_at
            FROM bonuses
            WHERE user_id = %s
              AND created_at >= %s::date
              AND created_at < %s::date
            ORDER BY created_at ASC
            """,
            (user_id, start_month, end_month),
        ).fetchall()]

    base_salary_net = _latest_base_salary(user_id)

    if profile:
        hourly_rate = float(profile["hourly_rate"] or 0)
        weekly_hours = float(profile["regular_hours_per_week"] or 0)
        base_monthly_gross = hourly_rate * weekly_hours * 4.333
    else:
        hourly_rate = 0.0
        weekly_hours = 0.0
        base_monthly_gross = base_salary_net

    # Regla V1:
    # - Si hay perfil laboral, el salario base se calcula desde hourly_rate y rebajos reales.
    # - La tabla salaries solo se usa como respaldo si no hay perfil laboral.
    fixed_deduction_details = []
    fixed_deductions_total = 0.0
    if base_salary_net > 0 and not profile:
        base_monthly_net = base_salary_net
    else:
        for deduction in deductions:
            amount = _as_float(deduction.get("amount"))
            deduction_type = str(deduction.get("deduction_type") or "").lower().strip()
            if deduction_type == "percentage":
                calculated = base_monthly_gross * (amount / 100)
            else:
                calculated = _monthly_amount_from_frequency(amount, deduction.get("frequency"))
            fixed_deductions_total += calculated
            fixed_deduction_details.append({
                "name": deduction.get("name"),
                "deduction_type": deduction_type or "fixed",
                "base_amount": amount,
                "frequency": deduction.get("frequency"),
                "calculated_monthly_amount": calculated,
                "applies_to": "base_salary",
            })
        base_monthly_net = max(base_monthly_gross - fixed_deductions_total, 0)

    positive_payroll_gross = sum(max(_as_float(event.get("amount")), 0) for event in payroll_events)
    vgh_gross = sum(min(_as_float(event.get("amount")), 0) for event in payroll_events)
    bonuses_gross = sum(_as_float(item.get("amount")) for item in current_bonuses)

    extra_base = positive_payroll_gross + max(bonuses_gross, 0)
    extra_deductions_total, extra_deduction_details = _variable_payroll_deductions(
        extra_base,
        deductions,
    )

    if extra_base > 0:
        payroll_extra_deduction = extra_deductions_total * (positive_payroll_gross / extra_base)
        bonus_deduction = extra_deductions_total * (max(bonuses_gross, 0) / extra_base)
    else:
        payroll_extra_deduction = 0.0
        bonus_deduction = 0.0

    # VGH es tiempo no trabajado: resta bruto directo y no recibe rebajo positivo.
    payroll_events_gross = positive_payroll_gross + vgh_gross
    payroll_events_net = (positive_payroll_gross - payroll_extra_deduction) + vgh_gross
    bonuses_net = bonuses_gross - bonus_deduction if bonuses_gross > 0 else bonuses_gross

    projected_gross = base_monthly_gross + payroll_events_gross + bonuses_gross
    projected_net = base_monthly_net + payroll_events_net + bonuses_net

    return {
        "status": "OK" if (base_monthly_net > 0 or profile) else "MISSING_BASE_SALARY",
        "month": start_month[:7],
        "base": {
            "hourly_rate": hourly_rate,
            "regular_hours_per_week": weekly_hours,
            "base_monthly_gross": round(base_monthly_gross, 2),
            "base_monthly_net": round(base_monthly_net, 2),
            "base_salary_source": "salaries" if base_salary_net > 0 else "employment_profile",
        },
        "adjustments": {
            "payroll_events_total": round(payroll_events_gross, 2),
            "payroll_events_net": round(payroll_events_net, 2),
            "bonuses_gross": round(bonuses_gross, 2),
            "bonuses_net": round(bonuses_net, 2),
            "projected_gross": round(projected_gross, 2),
            "events": payroll_events,
            "bonuses": current_bonuses,
        },
        "deductions": {
            "total_deductions": round(fixed_deductions_total + extra_deductions_total, 2),
            "fixed_deductions_total": round(fixed_deductions_total, 2),
            "extra_deductions_total": round(extra_deductions_total, 2),
            "details": fixed_deduction_details + extra_deduction_details,
        },
        "results": {
            "base_net": round(base_monthly_net, 2),
            "projected_net": round(projected_net, 2),
            "current_month_adjustments_net": round(projected_net - base_monthly_net, 2),
            "current_month_adjustments_gross": round(payroll_events_gross + bonuses_gross, 2),
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
            WHERE id = %s
            AND user_id = %s
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
            WHERE id = %s
            AND user_id = %s
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
    category = normalize_category(category, "expense")
    if not expense_type or expense_type == "variable":
        expense_type = expense_type_for_category(category)

    with get_connection() as conn:
        expense = conn.execute(
            """
            SELECT id
            FROM expenses
            WHERE id = %s
            AND user_id = %s
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
            SET category = %s,
                amount = %s,
                expense_type = %s,
                description = %s
            WHERE id = %s
            AND user_id = %s
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
            WHERE id = %s
            AND user_id = %s
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
            WHERE debt_id = %s
            """,
            (debt_id,)
        )

        conn.execute(
            """
            DELETE FROM debts
            WHERE id = %s
            AND user_id = %s
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
    payment_day: int | None = None,
    start_date: str | None = None,
    first_payment_date: str | None = None,
    installments_paid: int = 0,
    auto_update_monthly: bool = True,
):
    user_id = get_current_user_id()

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, installments_paid, start_date, first_payment_date
            FROM debts
            WHERE id = %s
            AND user_id = %s
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
            SET name = %s,
                debt_type = %s,
                total_amount = %s,
                remaining_amount = %s,
                monthly_payment = %s,
                interest_rate = %s,
                term_months = %s,
                payment_day = %s,
                start_date = %s,
                first_payment_date = %s,
                auto_update_monthly = %s,
                installments_paid = %s,
                updated_at = NOW()
            WHERE id = %s
            AND user_id = %s
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
                (_parse_date(start_date) or _parse_date(debt.get("start_date")) or date.today()).isoformat(),
                (_parse_date(first_payment_date) or _parse_date(debt.get("first_payment_date")) or _default_first_payment_date(_parse_date(start_date) or _parse_date(debt.get("start_date")) or date.today(), payment_day)).isoformat(),
                auto_update_monthly,
                max(int(installments_paid or 0), 0),
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
        "start_date": (_parse_date(start_date) or _parse_date(debt.get("start_date")) or date.today()).isoformat(),
        "first_payment_date": (_parse_date(first_payment_date) or _parse_date(debt.get("first_payment_date")) or _default_first_payment_date(_parse_date(start_date) or _parse_date(debt.get("start_date")) or date.today(), payment_day)).isoformat(),
        "installments_paid": max(int(installments_paid or 0), 0),
        "auto_update_monthly": auto_update_monthly,
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
    user_id = get_current_user_id()

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount,
                   monthly_payment, interest_rate, term_months, payment_day, user_id
            FROM debts
            WHERE id = %s
            AND user_id = %s
            """,
            (debt_id, user_id)
        ).fetchone()

        if not debt:
            return {
                "message": "Deuda no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        previous_remaining_amount = _as_float(debt["remaining_amount"])
        previous_monthly_payment = _as_float(debt["monthly_payment"])

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
            SET remaining_amount = %s, monthly_payment = %s, updated_at = NOW()
            WHERE id = %s
            AND user_id = %s
            """,
            (
                final_remaining_amount,
                final_monthly_payment,
                debt_id,
                user_id
            )
        )

        cursor = conn.execute(
            """
            INSERT INTO debt_payments (
                user_id,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                user_id,
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
        "user_id": user_id,
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
            WHERE lower(name) LIKE %s
            AND user_id = %s
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
    user_id = get_current_user_id()

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount,
                   monthly_payment, interest_rate, term_months, payment_day, user_id
            FROM debts
            WHERE id = %s
            AND user_id = %s
            """,
            (debt_id, user_id)
        ).fetchone()

        if not debt:
            return {
                "message": "Deuda no encontrada o no pertenece al usuario actual.",
                "status": "ERROR"
            }

        previous_remaining_amount = _as_float(debt["remaining_amount"])
        previous_monthly_payment = _as_float(debt["monthly_payment"])

        final_monthly_payment = (
            new_monthly_payment
            if new_monthly_payment is not None
            else previous_monthly_payment
        )

        conn.execute(
            """
            UPDATE debts
            SET remaining_amount = %s, monthly_payment = %s,
                installments_paid = COALESCE(installments_paid, 0) + 1,
                updated_at = NOW()
            WHERE id = %s
            AND user_id = %s
            """,
            (
                new_remaining_amount,
                final_monthly_payment,
                debt_id,
                user_id
            )
        )

        cursor = conn.execute(
            """
            INSERT INTO debt_payments (
                user_id,
                debt_id,
                payment_type,
                amount,
                previous_remaining_amount,
                new_remaining_amount,
                previous_monthly_payment,
                new_monthly_payment,
                description,
                payment_date,
                installment_number,
                source,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE((SELECT installments_paid FROM debts WHERE id = %s), 1),
                    'manual', NOW())
            """,
            (
                user_id,
                debt_id,
                "monthly_payment",
                amount,
                previous_remaining_amount,
                new_remaining_amount,
                previous_monthly_payment,
                final_monthly_payment,
                description,
                date.today().isoformat(),
                debt_id,
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
        "user_id": user_id,
        "status": "OK"
    }

def get_debt_payments(debt_id: int | None = None):
    user_id = get_current_user_id()

    with get_connection() as conn:
        if debt_id:
            rows = conn.execute(
                """
                SELECT id, user_id, debt_id, payment_type, amount, previous_remaining_amount,
                       new_remaining_amount, previous_monthly_payment,
                       new_monthly_payment, principal_amount, interest_amount,
                       description, payment_date, installment_number, source, created_at
                FROM debt_payments
                WHERE debt_id = %s
                AND user_id = %s
                ORDER BY id DESC
                """,
                (debt_id, user_id)
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, user_id, debt_id, payment_type, amount, previous_remaining_amount,
                       new_remaining_amount, previous_monthly_payment,
                       new_monthly_payment, principal_amount, interest_amount,
                       description, payment_date, installment_number, source, created_at
                FROM debt_payments
                WHERE user_id = %s
                ORDER BY id DESC
                """,
                (user_id,)
            ).fetchall()

    return [dict(row) for row in rows]

def get_net_worth_report():
    """Reporte de patrimonio tolerante a listas vacías y NUMERIC de PostgreSQL."""
    user_id = get_current_user_id()

    with get_connection() as conn:
        savings = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id
            FROM savings
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

        investments = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id
            FROM investments
            WHERE user_id = %s
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
            WHERE user_id = %s
            ORDER BY remaining_amount DESC
            """,
            (user_id,)
        ).fetchall()

    savings_list = [dict(row) for row in savings]
    investments_list = [dict(row) for row in investments]
    debts_list = [dict(row) for row in debts]

    savings_total = _safe_sum(savings_list, "amount")
    investments_total = _safe_sum(investments_list, "amount")
    assets_total = savings_total + investments_total

    debt_total = _safe_sum(debts_list, "remaining_amount")
    monthly_debt_payments = _safe_sum(debts_list, "monthly_payment")

    net_worth = assets_total - debt_total

    if net_worth < 0:
        status = "negative"
        interpretation = "Tu patrimonio neto es negativo porque tus deudas superan tus activos."
    elif net_worth == 0:
        status = "neutral"
        interpretation = "Todavía no hay suficiente información financiera registrada o tus activos cubren exactamente tus deudas."
    else:
        status = "positive"
        interpretation = "Tu patrimonio neto es positivo. Tus activos registrados superan tus deudas."

    if not savings_list and not investments_list and not debts_list:
        risk_level = "unknown"
        priority = "Ingresar datos financieros iniciales para calcular tu estado real."
    elif debt_total > 0 and assets_total == 0:
        risk_level = "high"
        priority = "Registrar activos reales si existen y priorizar reducción de deuda."
    elif debt_total > assets_total:
        risk_level = "medium_high"
        priority = "Reducir deudas de mayor interés y aumentar activos líquidos."
    elif debt_total == 0:
        risk_level = "low"
        priority = "Mantener activos, crear fondo de emergencia e invertir de forma ordenada."
    else:
        risk_level = "medium"
        priority = "Mantener control de deuda y seguir aumentando patrimonio."

    debt_to_asset_ratio = debt_total / assets_total if assets_total > 0 else None
    highest_debt = debts_list[0] if debts_list else None

    recommendations = []

    if not savings_list and not investments_list and not debts_list:
        recommendations.append("Ingresar deudas, ahorros, inversiones e ingresos para activar el dashboard real.")
    elif assets_total == 0:
        recommendations.append("Registrar ahorros, inversiones o saldos disponibles reales para que el patrimonio sea más preciso.")

    if highest_debt:
        recommendations.append(
            f"Priorizar seguimiento de la deuda más grande: {highest_debt['name']} por ₡{_as_float(highest_debt.get('remaining_amount')):,.2f}."
        )

    high_interest_debts = [
        debt for debt in debts_list
        if _as_float(debt.get("interest_rate")) >= 20
    ]

    if high_interest_debts:
        recommendations.append("Revisar deudas con interés alto para aplicar avalancha o refinanciamiento.")

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
            "assets_total": assets_total,
        },
        "liabilities": {
            "debts": debts_list,
            "debt_total": debt_total,
            "monthly_debt_payments": monthly_debt_payments,
            "highest_debt": highest_debt,
            "high_interest_debts": high_interest_debts,
        },
        "net_worth": net_worth,
        "status": status,
        "risk_level": risk_level,
        "interpretation": interpretation,
        "priority": priority,
        "recommendations": recommendations,
        "ratios": {
            "debt_to_asset_ratio": debt_to_asset_ratio,
        },
        "setup": {
            "has_assets": bool(savings_list or investments_list),
            "has_debts": bool(debts_list),
            "has_any_financial_data": bool(savings_list or investments_list or debts_list),
        },
        "user_id": user_id,
    }

def get_user_status():
    """Estado general del usuario, funcionando aunque la base esté vacía."""
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
            AND user_id = %s
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
    critical_goals = [goal for goal in goals_list if goal.get("priority") == "critical"]

    total_goals_remaining = sum(
        max(_as_float(goal.get("target_amount")) - _as_float(goal.get("current_amount")), 0)
        for goal in goals_list
    )

    most_urgent_goal = goals_list[0] if goals_list else None

    setup = {
        "has_income_profile": summary.get("setup", {}).get("has_income_profile", False),
        "has_financial_data": summary.get("setup", {}).get("has_financial_data", False),
        "has_goals": bool(goals_list),
        "is_empty": not summary.get("setup", {}).get("has_financial_data", False) and not goals_list,
    }

    return {
        "income": {
            "monthly_net_income": summary["income"]["projected_net_income"],
            "total_income": summary["income"]["total_income"],
        },
        "assets": {
            "savings": net_worth["assets"]["savings_total"],
            "investments": net_worth["assets"]["investments_total"],
            "assets_total": net_worth["assets"]["assets_total"],
            "net_worth": net_worth["net_worth"],
        },
        "debts": {
            "total": net_worth["liabilities"]["debt_total"],
            "monthly_payments": net_worth["liabilities"]["monthly_debt_payments"],
            "highest_debt": (
                net_worth["liabilities"]["highest_debt"]["name"]
                if net_worth["liabilities"].get("highest_debt")
                else None
            ),
        },
        "expenses": {
            "fixed_expenses": summary["expenses"]["fixed_expenses_total"],
            "total_expenses": summary["expenses"]["expenses_total"],
        },
        "cashflow": {
            "available_cash": summary["results"]["available_cash"],
        },
        "goals": {
            "active_goals_count": active_goals_count,
            "critical_goals_count": len(critical_goals),
            "total_goals_remaining": total_goals_remaining,
            "most_urgent_goal": most_urgent_goal,
            "active_goals": goals_list,
        },
        "financial_health": {
            "status": net_worth["status"],
            "risk_level": net_worth["risk_level"],
        },
        "setup": setup,
        "user_id": user_id,
    }

def get_financial_dashboard():
    """Dashboard seguro para producción y para base recién limpia."""
    user_status = get_user_status()
    net_worth = get_net_worth_report()

    income = user_status["income"]
    expenses = user_status["expenses"]
    debts = user_status["debts"]
    cashflow = user_status["cashflow"]
    goals = user_status["goals"]
    financial_health = user_status["financial_health"]
    setup = user_status.get("setup", {})

    alerts = []
    quick_recommendations = []

    if setup.get("is_empty"):
        alerts.append({
            "type": "setup",
            "level": "info",
            "message": "Aún no hay datos financieros registrados para este usuario. Ingresa ingresos, deudas, gastos, ahorros o inversiones para activar el dashboard."
        })
        quick_recommendations.append("Configurar primero el perfil laboral o ingresar ingresos reales.")
        quick_recommendations.append("Luego registrar deudas, gastos fijos, ahorros e inversiones.")
    else:
        if financial_health["risk_level"] in ["high", "medium_high"]:
            alerts.append({
                "type": "risk",
                "level": "high" if financial_health["risk_level"] == "high" else "medium",
                "message": "Tu riesgo financiero requiere seguimiento por deudas o patrimonio negativo."
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
            quick_recommendations.append("Mantener pagos mínimos y priorizar deudas con mayor interés.")

        if goals["most_urgent_goal"]:
            quick_recommendations.append(f"Revisar progreso de la meta: {goals['most_urgent_goal']['name']}.")

        if cashflow["available_cash"] > 0:
            quick_recommendations.append("Distribuir el disponible entre meta crítica, deuda e imprevistos.")

    dashboard_cards = [
        {
            "title": "Ingreso mensual neto",
            "value": income["monthly_net_income"],
            "type": "currency",
            "status": "info" if setup.get("has_income_profile") else "empty"
        },
        {
            "title": "Disponible estimado",
            "value": cashflow["available_cash"],
            "type": "currency",
            "status": "empty" if setup.get("is_empty") else ("warning" if cashflow["available_cash"] < 100000 else "good")
        },
        {
            "title": "Gastos fijos",
            "value": expenses["fixed_expenses"],
            "type": "currency",
            "status": "empty" if expenses["fixed_expenses"] == 0 else "info"
        },
        {
            "title": "Deuda total",
            "value": debts["total"],
            "type": "currency",
            "status": "empty" if debts["total"] == 0 else "danger"
        },
        {
            "title": "Patrimonio neto",
            "value": user_status["assets"]["net_worth"],
            "type": "currency",
            "status": "empty" if setup.get("is_empty") else ("danger" if user_status["assets"]["net_worth"] < 0 else "good")
        },
        {
            "title": "Meta principal",
            "value": goals["most_urgent_goal"]["name"] if goals["most_urgent_goal"] else "Sin meta activa",
            "type": "text",
            "status": "warning" if goals["most_urgent_goal"] else "empty"
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
            "financial_health": financial_health,
            "setup": setup,
        },
        "status": "empty" if setup.get("is_empty") else "ok",
        "user_id": user_status.get("user_id"),
    }
