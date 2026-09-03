from datetime import date, datetime, timedelta
from typing import Any

from backend.core.database import get_connection
from backend.auth.current_user import get_current_user_id, get_current_workspace_id
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


def _aguinaldo_period(as_of: date | None = None) -> tuple[date, date]:
    """Período legal costarricense del aguinaldo: 1 dic. a 30 nov."""
    as_of = as_of or date.today()
    if as_of.month == 12:
        return date(as_of.year, 12, 1), date(as_of.year + 1, 11, 30)
    return date(as_of.year - 1, 12, 1), date(as_of.year, 11, 30)


def _build_aguinaldo_report(rows: list[dict], as_of: date | None = None) -> dict:
    """Calcula el acumulado desde ingresos salariales reales, nunca desde SINPE genéricos."""
    as_of = as_of or date.today()
    period_start, period_end = _aguinaldo_period(as_of)
    # El salario del mes en curso aún no está cerrado ni reportado por la CCSS.
    cutoff = period_end if as_of >= period_end else as_of.replace(day=1) - timedelta(days=1)
    monthly: dict[str, dict] = {}
    source_totals = {"ccss_salary": 0.0, "salary": 0.0, "payroll_event": 0.0, "bonus": 0.0}

    for raw in rows:
        earned_on = raw.get("earned_on")
        if isinstance(earned_on, datetime):
            earned_on = earned_on.date()
        elif not isinstance(earned_on, date):
            try:
                earned_on = datetime.fromisoformat(str(earned_on)[:10]).date()
            except (TypeError, ValueError):
                continue
        if earned_on < period_start or earned_on > cutoff:
            continue

        kind = str(raw.get("kind") or "salary")
        amount = _as_float(raw.get("amount"))
        source_totals[kind] = source_totals.get(kind, 0.0) + amount
        month_key = earned_on.strftime("%Y-%m")
        bucket = monthly.setdefault(month_key, {
            "month": month_key, "salary": 0.0, "payroll_events": 0.0,
            "bonuses": 0.0, "total_earned": 0.0, "entries": 0,
        })
        bucket_key = {"ccss_salary": "salary", "salary": "salary", "payroll_event": "payroll_events", "bonus": "bonuses"}.get(kind, "salary")
        bucket[bucket_key] += amount
        bucket["total_earned"] += amount
        bucket["entries"] += 1

    earned_total = sum(source_totals.values())
    months = []
    cursor = period_start.replace(day=1)
    last_month = cutoff.replace(day=1)
    while cursor <= last_month:
        key = cursor.strftime("%Y-%m")
        bucket = monthly.get(key, {
            "month": key, "salary": 0.0, "payroll_events": 0.0,
            "bonuses": 0.0, "total_earned": 0.0, "entries": 0,
        })
        months.append({name: round(value, 2) if isinstance(value, float) else value for name, value in bucket.items()})
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)

    return {
        "status": "OK" if rows else "NO_SALARY_DATA",
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat(), "calculated_through": cutoff.isoformat()},
        "formula": "Total de salarios ordinarios y extraordinarios del período / 12",
        "earned_salary_total": round(earned_total, 2),
        "accrued_aguinaldo": round(earned_total / 12, 2),
        "source_totals": {key: round(value, 2) for key, value in source_totals.items()},
        "months": months,
        "missing_months": [item["month"] for item in months if item["entries"] == 0],
    }


def _financial_cycle_bounds(today: date | None = None, closing_day: int = 5) -> tuple[date, date]:
    """Operating view closes *through* day 5 and rolls on day 6.

    Returned end is exclusive. Example: Jul 6 <= date < Aug 6 represents the
    view that remains active through Aug 5. On Aug 6 the next cycle begins.
    """
    today = today or date.today()
    start_day = closing_day + 1
    if today.day >= start_day:
        start = today.replace(day=start_day)
        if today.month == 12:
            end = date(today.year + 1, 1, start_day)
        else:
            end = date(today.year, today.month + 1, start_day)
    else:
        end = today.replace(day=start_day)
        if today.month == 1:
            start = date(today.year - 1, 12, start_day)
        else:
            start = date(today.year, today.month - 1, start_day)
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


def _latest_base_salary(workspace_id: str) -> float:
    """Base mensual fija. Preferimos un salario base guardado; no depende de que entren transacciones bancarias."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT amount, source
            FROM salaries
            WHERE workspace_id = %s
            ORDER BY
                CASE
                    WHEN LOWER(source) LIKE '%%base%%' THEN 0
                    WHEN LOWER(source) LIKE '%%mensual%%' THEN 1
                    ELSE 2
                END,
                id DESC
            LIMIT 1
            """,
            (workspace_id,),
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


def _interest_for_period(
    balance: float,
    annual_rate: float,
    interest_method: str = "monthly",
    previous_date: date | None = None,
    payment_date: date | None = None,
) -> float:
    balance = max(_as_float(balance), 0)
    annual_rate = max(_as_float(annual_rate), 0)
    if balance <= 0 or annual_rate <= 0:
        return 0.0

    method = str(interest_method or "monthly").strip().lower()
    if method == "daily_365":
        end = payment_date or date.today()
        start = previous_date or (end - timedelta(days=30))
        days = max((end - start).days, 1)
        return round(balance * (annual_rate / 100) * days / 365, 2)

    return round(balance * (annual_rate / 100) / 12, 2)


def _scheduled_payment_breakdown(
    balance: float,
    payment: float,
    annual_rate: float,
    fixed_fee_amount: float = 0,
    interest_method: str = "monthly",
    previous_date: date | None = None,
    payment_date: date | None = None,
) -> tuple[float, float, float, float, float]:
    """Return (actual_payment, principal, interest, fee, extra_principal).

    `monthly_payment` is treated as the normal total cash payment. Interest and
    fixed fees are paid first; anything above the normal payment goes 100% to
    principal. This makes extraordinary payments reduce the debt immediately.
    """
    balance = max(_as_float(balance), 0)
    requested_payment = max(_as_float(payment), 0)
    fee = min(max(_as_float(fixed_fee_amount), 0), requested_payment)
    interest = _interest_for_period(
        balance, annual_rate, interest_method, previous_date, payment_date
    )

    normal_payment = requested_payment
    principal_budget = max(normal_payment - fee - interest, 0)
    principal = min(round(principal_budget, 2), balance)
    actual_payment = round(min(normal_payment, fee + interest + balance), 2)
    return actual_payment, round(principal, 2), round(interest, 2), round(fee, 2), 0.0


def _payment_breakdown_with_extra(
    balance: float,
    amount_paid: float,
    scheduled_payment: float,
    annual_rate: float,
    fixed_fee_amount: float = 0,
    interest_method: str = "monthly",
    previous_date: date | None = None,
    payment_date: date | None = None,
) -> tuple[float, float, float, float, float]:
    amount_paid = max(_as_float(amount_paid), 0)
    scheduled_payment = max(_as_float(scheduled_payment), 0)
    fee = min(max(_as_float(fixed_fee_amount), 0), amount_paid)
    interest = _interest_for_period(
        balance, annual_rate, interest_method, previous_date, payment_date
    )

    normal_cash = min(amount_paid, scheduled_payment or amount_paid)
    normal_principal = max(normal_cash - fee - interest, 0)
    normal_principal = min(round(normal_principal, 2), max(_as_float(balance), 0))

    extra_cash = max(amount_paid - normal_cash, 0)
    remaining_after_normal = max(_as_float(balance) - normal_principal, 0)
    extra_principal = min(round(extra_cash, 2), remaining_after_normal)
    principal = round(normal_principal + extra_principal, 2)
    actual_payment = round(min(amount_paid, fee + interest + principal), 2)
    return actual_payment, principal, round(interest, 2), round(fee, 2), round(extra_principal, 2)


def _sync_automatic_debt_payments(user_id: int, workspace_id: str | None = None) -> None:
    """Sincroniza cuotas vencidas usando fechas reales y un libro de pagos idempotente.

    La fecha de inicio, primera cuota, día de pago y fecha actual determinan cuántas
    cuotas debieron aplicarse. Cada cuota se registra una sola vez en debt_payments.
    """
    workspace_id = workspace_id or get_current_workspace_id()
    today = date.today()
    with get_connection() as conn:
        debts = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount, monthly_payment,
                   interest_rate, term_months, payment_day, start_date, first_payment_date,
                   auto_update_monthly, installments_paid, created_at, last_payment_date,
                   interest_method, fixed_fee_amount
            FROM debts
            WHERE workspace_id = %s
              AND COALESCE(auto_update_monthly, TRUE) = TRUE
              AND remaining_amount > 0
            ORDER BY id
            """,
            (workspace_id,),
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
                WHERE workspace_id = %s AND debt_id = %s AND payment_type = 'monthly_payment'
                ORDER BY installment_number, payment_date
                """,
                (workspace_id, debt["id"]),
            ).fetchall()
            existing_dates = {str(row.get("payment_date"))[:10] for row in payment_rows if row.get("payment_date")}
            ledger_paid = max([int(row.get("installment_number") or 0) for row in payment_rows] or [0])
            paid_count = max(int(debt.get("installments_paid") or 0), ledger_paid)
            balance = _as_float(debt.get("remaining_amount"))
            monthly_payment = _normalize_debt_payment_value(debt.get("monthly_payment"), balance)
            if monthly_payment <= 0:
                continue

            # El valor histórico guardado actúa como ancla; solo creamos cuotas posteriores.
            previous_payment_date = _parse_date(debt.get("last_payment_date"))
            for installment_number in range(paid_count + 1, target_paid + 1):
                due = _add_months(first_due, installment_number - 1, payment_day)
                if due.isoformat() in existing_dates:
                    paid_count = max(paid_count, installment_number)
                    continue

                previous_balance = balance
                previous_due = previous_payment_date or _add_months(due, -1, payment_day)
                actual_payment, principal, interest, fee, extra_principal = _scheduled_payment_breakdown(
                    balance,
                    monthly_payment,
                    debt.get("interest_rate"),
                    debt.get("fixed_fee_amount"),
                    debt.get("interest_method") or "monthly",
                    previous_due,
                    due,
                )
                if principal <= 0:
                    break
                balance = round(max(balance - principal, 0), 2)

                conn.execute(
                    """
                    INSERT INTO debt_payments (
                        user_id, workspace_id, debt_id, payment_type, amount, principal_amount, interest_amount,
                        fee_amount, extra_principal_amount, previous_remaining_amount, new_remaining_amount,
                        previous_monthly_payment, new_monthly_payment, description,
                        payment_date, installment_number, source, created_at
                    )
                    SELECT %s, %s, %s, 'monthly_payment', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'auto_schedule', NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM debt_payments
                        WHERE workspace_id = %s AND debt_id = %s
                          AND payment_type = 'monthly_payment' AND payment_date = %s
                    )
                    """,
                    (
                        user_id, workspace_id, debt["id"], actual_payment, principal, interest, fee, extra_principal, previous_balance, balance,
                        monthly_payment, monthly_payment,
                        f"Cuota automática {installment_number}/{term or '?'} de {debt.get('name') or 'deuda'}",
                        due.isoformat(), installment_number,
                        workspace_id, debt["id"], due.isoformat(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO transactions (
                        user_id, workspace_id, transaction_date, description, amount, transaction_type,
                        category, account, source, notes, created_at
                    )
                    SELECT %s, %s, %s, %s, %s, 'debt_payment', %s, NULL, 'auto_debt_schedule', %s, NOW()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM transactions
                        WHERE workspace_id = %s AND source = 'auto_debt_schedule' AND notes = %s
                    )
                    """,
                    (
                        user_id, workspace_id, due.isoformat(), f"Cuota {debt.get('name') or 'deuda'}", actual_payment,
                        debt.get("name") or "Deudas", f"debt_id:{debt['id']};installment:{installment_number}",
                        workspace_id, f"debt_id:{debt['id']};installment:{installment_number}",
                    ),
                )
                paid_count = installment_number
                previous_payment_date = due
                existing_dates.add(due.isoformat())
                changed = True

            # Siempre normalizamos fechas, saldo y contador. El saldo solo avanza
            # mediante cuotas registradas en este libro, por lo que es idempotente.
            last_due = previous_payment_date or _parse_date(debt.get("last_payment_date"))
            finished = balance <= 0 or (term and paid_count >= term)
            next_due = None if finished else _add_months(first_due, paid_count, payment_day)
            conn.execute(
                """
                UPDATE debts
                SET start_date = COALESCE(start_date, %s),
                    first_payment_date = COALESCE(first_payment_date, %s),
                    remaining_amount = %s,
                    installments_paid = %s,
                    last_payment_date = %s,
                    next_payment_date = %s,
                    auto_update_monthly = CASE WHEN %s THEN FALSE ELSE auto_update_monthly END,
                    updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                """,
                (
                    start_date.isoformat(), first_due.isoformat(), balance, paid_count,
                    last_due.isoformat() if last_due else None,
                    next_due.isoformat() if next_due else None,
                    bool(finished), debt["id"], workspace_id,
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
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO salaries (amount, source, user_id, workspace_id, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (amount, source, user_id, workspace_id)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "amount": amount,
        "source": source,
        "user_id": user_id,
        "workspace_id": workspace_id
    }


def get_salaries():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, source, user_id, workspace_id, created_at
            FROM salaries
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def add_bonus(amount: float, description: str = ""):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bonuses (amount, description, user_id, workspace_id, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (amount, description, user_id, workspace_id)
        )
        conn.commit()

    return {
        "id": cursor.lastrowid,
        "amount": amount,
        "description": description,
        "user_id": user_id,
        "workspace_id": workspace_id
    }


def get_bonuses():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, description, user_id, workspace_id, created_at
            FROM bonuses
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def calculate_aguinaldo(as_of: date | None = None):
    """Aguinaldo: Orden Patronal CCSS primero; registros internos solo como respaldo."""
    workspace_id = get_current_workspace_id()
    period_start, period_end = _aguinaldo_period(as_of)
    calculation_date = as_of or date.today()
    completed_through = period_end if calculation_date >= period_end else calculation_date.replace(day=1) - timedelta(days=1)
    cutoff = completed_through + timedelta(days=1)

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payroll_salary_reports (
                id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, workspace_id UUID NOT NULL,
                email_message_id BIGINT, provider_message_id TEXT, period_month TEXT NOT NULL,
                reported_salary NUMERIC NOT NULL, trans_previous_salary NUMERIC,
                previous_salary NUMERIC, daily_subsidy NUMERIC, employer_number TEXT,
                verification_code TEXT, source TEXT NOT NULL DEFAULT 'ccss_order_patronal',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(workspace_id, period_month), UNIQUE(workspace_id, provider_message_id)
            )
            """
        )
        rows = [dict(row) for row in conn.execute(
            """
            SELECT 'ccss_salary' AS kind, reported_salary AS amount,
                   TO_DATE(period_month || '-01', 'YYYY-MM-DD') AS earned_on,
                   'Orden Patronal CCSS' AS description
            FROM payroll_salary_reports
            WHERE workspace_id = %s
              AND TO_DATE(period_month || '-01', 'YYYY-MM-DD') >= %s::date
              AND TO_DATE(period_month || '-01', 'YYYY-MM-DD') < %s::date
            UNION ALL
            SELECT 'salary' AS kind, amount, created_at::date AS earned_on, source AS description
            FROM salaries
            WHERE workspace_id = %s AND created_at >= %s::date AND created_at < %s::date
              AND NOT EXISTS (
                  SELECT 1 FROM payroll_salary_reports r
                  WHERE r.workspace_id = salaries.workspace_id
                    AND r.period_month = TO_CHAR(salaries.created_at, 'YYYY-MM')
              )
            UNION ALL
            SELECT 'payroll_event' AS kind, amount, created_at::date AS earned_on, description
            FROM payroll_events
            WHERE workspace_id = %s AND created_at >= %s::date AND created_at < %s::date
              AND NOT EXISTS (
                  SELECT 1 FROM payroll_salary_reports r
                  WHERE r.workspace_id = payroll_events.workspace_id
                    AND r.period_month = TO_CHAR(payroll_events.created_at, 'YYYY-MM')
              )
            UNION ALL
            SELECT 'bonus' AS kind, amount, created_at::date AS earned_on, description
            FROM bonuses
            WHERE workspace_id = %s AND created_at >= %s::date AND created_at < %s::date
              AND NOT EXISTS (
                  SELECT 1 FROM payroll_salary_reports r
                  WHERE r.workspace_id = bonuses.workspace_id
                    AND r.period_month = TO_CHAR(bonuses.created_at, 'YYYY-MM')
              )
            ORDER BY earned_on ASC
            """,
            (workspace_id, period_start, cutoff, workspace_id, period_start, cutoff,
             workspace_id, period_start, cutoff, workspace_id, period_start, cutoff),
        ).fetchall()]
    return _build_aguinaldo_report(rows, as_of)


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
    interest_method: str = "monthly",
    fixed_fee_amount: float = 0,
):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
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
                interest_method,
                fixed_fee_amount,
                user_id,
                workspace_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
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
                str(interest_method or "monthly"),
                max(_as_float(fixed_fee_amount), 0),
                user_id,
                workspace_id
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
        "interest_method": str(interest_method or "monthly"),
        "fixed_fee_amount": max(_as_float(fixed_fee_amount), 0),
        "user_id": user_id,
        "workspace_id": workspace_id
    }


def get_debts():
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    _sync_automatic_debt_payments(user_id, workspace_id)

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
                   next_payment_date,
                   last_payment_date,
                   auto_update_monthly,
                   installments_paid,
                   interest_method,
                   fixed_fee_amount,
                   updated_at,
                   created_at,
                   user_id,
                   workspace_id
            FROM debts
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
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
            WHERE workspace_id = %s
            GROUP BY debt_id
            """,
            (workspace_id,),
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
        stored_last = _parse_date(debt.get("last_payment_date"))
        stored_next = _parse_date(debt.get("next_payment_date"))
        ledger_last = _parse_date(stat.get("last_payment_date"))
        debt["last_payment_date"] = (ledger_last or stored_last).isoformat() if (ledger_last or stored_last) else None
        debt["next_payment_date"] = (stored_next or next_due).isoformat() if (stored_next or next_due) else None
        debt["total_installments"] = total_installments
        debt["paid_installments"] = paid_installments
        debt["remaining_installments"] = max(total_installments - paid_installments, 0) if total_installments else None
        debt["progress_percent"] = round((paid_installments / total_installments) * 100, 2) if total_installments else 0
        debt["schedule_status"] = "paid" if _as_float(debt.get("remaining_amount")) <= 0 else ("current" if not next_due or next_due > today else "due")
    return debts


def add_saving(name: str, amount: float):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO savings (name, amount, user_id, workspace_id, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            RETURNING id, name, amount, created_at, user_id, workspace_id
            """,
            (name, amount, user_id, workspace_id)
        ).fetchone()
        conn.commit()

    return dict(row)


def get_savings():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id, workspace_id
            FROM savings
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def update_saving(saving_id: int, name: str, amount: float):
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        saving = conn.execute(
            """
            SELECT id FROM savings
            WHERE id = %s AND workspace_id = %s
            """,
            (saving_id, workspace_id)
        ).fetchone()

        if not saving:
            return {"message": "Ahorro no encontrado o no pertenece al workspace actual.", "status": "ERROR"}

        row = conn.execute(
            """
            UPDATE savings
            SET name = %s, amount = %s
            WHERE id = %s AND workspace_id = %s
            RETURNING id, name, amount, created_at, user_id, workspace_id
            """,
            (name, amount, saving_id, workspace_id)
        ).fetchone()
        conn.commit()

    result = dict(row)
    result.update({"message": "Ahorro actualizado correctamente.", "status": "OK"})
    return result


def delete_saving(saving_id: int):
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        saving = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id, workspace_id
            FROM savings
            WHERE id = %s AND workspace_id = %s
            """,
            (saving_id, workspace_id)
        ).fetchone()

        if not saving:
            return {"message": "Ahorro no encontrado o no pertenece al workspace actual.", "status": "ERROR"}

        conn.execute(
            """
            DELETE FROM savings
            WHERE id = %s AND workspace_id = %s
            """,
            (saving_id, workspace_id)
        )
        conn.commit()

    return {"message": "Ahorro eliminado correctamente.", "deleted_saving": dict(saving), "status": "OK"}


def add_investment(name: str, amount: float):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO investments (name, amount, user_id, workspace_id, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            RETURNING id, name, amount, created_at, user_id, workspace_id
            """,
            (name, amount, user_id, workspace_id)
        ).fetchone()
        conn.commit()

    return dict(row)


def get_investments():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id, workspace_id
            FROM investments
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def update_investment(investment_id: int, name: str, amount: float):
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        investment = conn.execute(
            """
            SELECT id FROM investments
            WHERE id = %s AND workspace_id = %s
            """,
            (investment_id, workspace_id)
        ).fetchone()

        if not investment:
            return {"message": "Inversión no encontrada o no pertenece al workspace actual.", "status": "ERROR"}

        row = conn.execute(
            """
            UPDATE investments
            SET name = %s, amount = %s
            WHERE id = %s AND workspace_id = %s
            RETURNING id, name, amount, created_at, user_id, workspace_id
            """,
            (name, amount, investment_id, workspace_id)
        ).fetchone()
        conn.commit()

    result = dict(row)
    result.update({"message": "Inversión actualizada correctamente.", "status": "OK"})
    return result


def delete_investment(investment_id: int):
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        investment = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id, workspace_id
            FROM investments
            WHERE id = %s AND workspace_id = %s
            """,
            (investment_id, workspace_id)
        ).fetchone()

        if not investment:
            return {"message": "Inversión no encontrada o no pertenece al workspace actual.", "status": "ERROR"}

        conn.execute(
            """
            DELETE FROM investments
            WHERE id = %s AND workspace_id = %s
            """,
            (investment_id, workspace_id)
        )
        conn.commit()

    return {"message": "Inversión eliminada correctamente.", "deleted_investment": dict(investment), "status": "OK"}

def add_expense(
    category: str,
    amount: float,
    expense_type: str = "variable",
    description: str = ""
):
    user_id = get_current_user_id()  # legacy compatibility during migration
    workspace_id = get_current_workspace_id()
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
                workspace_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                category,
                expense_type,
                description,
                amount,
                user_id,
                workspace_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "category": category,
        "expense_type": expense_type,
        "description": description,
        "amount": amount,
        "user_id": user_id,
        "workspace_id": workspace_id
    }


def get_expenses():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id,
                   category,
                   expense_type,
                   description,
                   amount,
                   created_at,
                   user_id,
                   workspace_id
            FROM expenses
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_financial_summary():
    """
    Resumen financiero tolerante a base vacía.
    Si el usuario aún no configuró perfil laboral, ingresos, gastos o deudas,
    devuelve ceros en vez de romper el dashboard.
    """
    workspace_id = get_current_workspace_id()

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
            WHERE workspace_id = %s
            """,
            (workspace_id,)
        ).fetchone()["total"]

        debt_total = conn.execute(
            """
            SELECT COALESCE(SUM(remaining_amount), 0) AS total
            FROM debts
            WHERE workspace_id = %s
            """,
            (workspace_id,)
        ).fetchone()["total"]

        monthly_debt_payments = conn.execute(
            """
            SELECT COALESCE(SUM(monthly_payment), 0) AS total
            FROM debts
            WHERE workspace_id = %s
            """,
            (workspace_id,)
        ).fetchone()["total"]

        savings_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM savings
            WHERE workspace_id = %s
            """,
            (workspace_id,)
        ).fetchone()["total"]

        investments_total = conn.execute(
            """
            SELECT COALESCE(
                (SELECT market_value FROM investment_portfolio_snapshots
                 WHERE workspace_id = %s ORDER BY snapshot_date DESC, id DESC LIMIT 1),
                (SELECT COALESCE(SUM(amount), 0) FROM investments WHERE workspace_id = %s),
                0
            ) AS total
            """,
            (workspace_id, workspace_id)
        ).fetchone()["total"]

        legacy_fixed_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'fixed'
            AND workspace_id = %s
            """,
            (workspace_id,)
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
            WHERE workspace_id = %s
              AND is_active = TRUE
              AND expected_amount IS NOT NULL
            """,
            (workspace_id,)
        ).fetchone()["total"]

        variable_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'variable'
            AND workspace_id = %s
            """,
            (workspace_id,)
        ).fetchone()["total"]

        one_time_expenses_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE expense_type = 'one_time'
            AND workspace_id = %s
            """,
            (workspace_id,)
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
        "workspace_id": workspace_id,
    }

def get_financial_cycle_report(as_of: date | None = None) -> dict:
    """Finance Overview anchored to the payment cycle (5 -> 5).

    The Overview has ONE active financial cycle. It only rolls on day 6.

    Example for 2026-08-26:
      - Financial/income cycle: 2026-08-05 through 2026-09-05 (inclusive).
      - Card expense statement: 2026-07-21 through 2026-08-21 (inclusive).

    The card cut on day 21 never changes the Overview by itself. Once the cut
    closes, that expense total is frozen until the financial cycle rolls on the
    6th. This mirrors the real workflow: the statement closes on the 21st and is
    paid with income accumulated through the following 5th.
    """
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    as_of = as_of or date.today()

    # Active Overview cycle. Day 5 belongs to the previous/open cycle; the
    # next cycle starts only on day 6.
    if as_of.day >= 6:
        cycle_start = date(as_of.year, as_of.month, 5)
        if as_of.month == 12:
            cycle_end_display = date(as_of.year + 1, 1, 5)
        else:
            cycle_end_display = date(as_of.year, as_of.month + 1, 5)
    else:
        cycle_end_display = date(as_of.year, as_of.month, 5)
        if as_of.month == 1:
            cycle_start = date(as_of.year - 1, 12, 5)
        else:
            cycle_start = date(as_of.year, as_of.month - 1, 5)

    # SQL end is exclusive so income on the 5th is included.
    cycle_end_exclusive = cycle_end_display + timedelta(days=1)

    # Expenses shown in this financial cycle are the BAC statement paid at its
    # ending day 5. For Aug 5 -> Sep 5, keep Jul 21 -> Aug 21 even after Aug 21.
    expense_end_display = date(cycle_start.year, cycle_start.month, 21)
    if expense_end_display.month == 1:
        expense_start = date(expense_end_display.year - 1, 12, 21)
    else:
        expense_start = date(expense_end_display.year, expense_end_display.month - 1, 21)
    expense_end_exclusive = expense_end_display + timedelta(days=1)
    expense_closed = as_of >= expense_end_exclusive

    # Debt synchronization is useful, but Finance must never collapse to zero
    # because a legacy debt row cannot be synchronized.
    try:
        _sync_automatic_debt_payments(user_id)
    except Exception:
        pass

    # Salary projection is optional infrastructure. A failure here must not hide
    # real transaction expenses already present in the database.
    try:
        salary_projection = calculate_monthly_salary_projection() or {}
    except Exception:
        salary_projection = {}
    projection_results = salary_projection.get("results", {}) or {}
    base_net = _as_float(projection_results.get("base_net"))
    if base_net <= 0:
        try:
            base_net = _latest_base_salary(workspace_id)
        except Exception:
            base_net = 0.0

    # Query each window directly. Do not fetch a broad range and then infer the
    # statement in Python; that was the source of the zero-expense regressions.
    with get_connection() as conn:
        expenses = [dict(row) for row in conn.execute(
            f"""
            SELECT id, transaction_date, description, amount, transaction_type,
                   category, account, source, notes, created_at
            FROM transactions
            WHERE workspace_id = %s
              AND LOWER(BTRIM(COALESCE(transaction_type, ''))) = 'expense'
              AND {_transaction_date_expr()} >= %s::date
              AND {_transaction_date_expr()} < %s::date
            ORDER BY {_transaction_date_expr()} DESC, id DESC
            """,
            (workspace_id, expense_start.isoformat(), expense_end_exclusive.isoformat()),
        ).fetchall()]

        debt_payments = [dict(row) for row in conn.execute(
            f"""
            SELECT id, transaction_date, description, amount, transaction_type,
                   category, account, source, notes, created_at
            FROM transactions
            WHERE workspace_id = %s
              AND LOWER(BTRIM(COALESCE(transaction_type, ''))) = 'debt_payment'
              AND {_transaction_date_expr()} >= %s::date
              AND {_transaction_date_expr()} < %s::date
            ORDER BY {_transaction_date_expr()} DESC, id DESC
            """,
            (workspace_id, cycle_start.isoformat(), cycle_end_exclusive.isoformat()),
        ).fetchall()]

        income_transactions = [dict(row) for row in conn.execute(
            f"""
            SELECT id, transaction_date, description, amount, transaction_type,
                   category, account, source, notes, created_at
            FROM transactions
            WHERE workspace_id = %s
              AND LOWER(BTRIM(COALESCE(transaction_type, ''))) = 'income'
              AND {_transaction_date_expr()} >= %s::date
              AND {_transaction_date_expr()} < %s::date
            ORDER BY {_transaction_date_expr()} DESC, id DESC
            """,
            (workspace_id, cycle_start.isoformat(), cycle_end_exclusive.isoformat()),
        ).fetchall()]

        loan_transactions = [dict(row) for row in conn.execute(
            f"""
            SELECT id, transaction_date, description, amount, transaction_type,
                   category, account, source, notes, created_at
            FROM transactions
            WHERE workspace_id = %s
              AND LOWER(BTRIM(COALESCE(transaction_type, ''))) IN ('loan_received', 'loan_disbursement')
              AND {_transaction_date_expr()} >= %s::date
              AND {_transaction_date_expr()} < %s::date
            ORDER BY {_transaction_date_expr()} DESC, id DESC
            """,
            (workspace_id, cycle_start.isoformat(), cycle_end_exclusive.isoformat()),
        ).fetchall()]

    # Extras are intentionally best-effort. They augment Net Income, but missing
    # payroll metadata cannot invalidate the Overview.
    extra_items: list[dict] = []
    extra_expected = 0.0
    try:
        with get_connection() as conn:
            payroll_events = [dict(row) for row in conn.execute(
                """
                SELECT id, event_type, hours, multiplier, amount, description, created_at
                FROM payroll_events
                WHERE workspace_id = %s
                ORDER BY created_at ASC
                """,
                (workspace_id,),
            ).fetchall()]
            bonuses = [dict(row) for row in conn.execute(
                """
                SELECT id, amount, description, created_at
                FROM bonuses
                WHERE workspace_id = %s
                ORDER BY created_at ASC
                """,
                (workspace_id,),
            ).fetchall()]

        for event in payroll_events:
            pay_date = _next_thursday_after_work_week(event.get("created_at"))
            if not pay_date or not (cycle_start <= pay_date < cycle_end_exclusive):
                continue
            net = _as_float(event.get("amount"))
            extra_expected += net
            extra_items.append({
                **event,
                "kind": "payroll_event",
                "estimated_pay_date": pay_date.isoformat(),
                "gross_amount": round(net, 2),
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
            if not pay_date or not (cycle_start <= pay_date < cycle_end_exclusive):
                continue
            net = _as_float(bonus.get("amount"))
            extra_expected += net
            extra_items.append({
                **bonus,
                "kind": "bonus",
                "estimated_pay_date": pay_date.isoformat(),
                "gross_amount": round(net, 2),
                "net_amount": round(net, 2),
            })
    except Exception:
        extra_items = []
        extra_expected = 0.0

    expenses_total = sum(_as_float(row.get("amount")) for row in expenses)
    debt_payments_total = sum(_as_float(row.get("amount")) for row in debt_payments)
    total_outflow = expenses_total + debt_payments_total
    income_received_total = sum(_as_float(row.get("amount")) for row in income_transactions)
    loans_total = sum(_as_float(row.get("amount")) for row in loan_transactions)
    expected_total = base_net + extra_expected

    try:
        from backend.finance.intelligence import calculate_goal_reserves, _fetch_active_goals
        goal_reserves = calculate_goal_reserves(_fetch_active_goals(workspace_id)) or {}
    except Exception:
        goal_reserves = {}
    goals_reserved = max(
        _as_float(goal_reserves.get("critical_monthly_required")),
        _as_float(goal_reserves.get("monthly_auto_reserve")),
    )

    real_balance = (
        expected_total
        + income_received_total
        + loans_total
        - total_outflow
        - goals_reserved
    )

    return {
        "status": "OK",
        "as_of": as_of.isoformat(),
        "cycle": {
            "start": cycle_start.isoformat(),
            "end": cycle_end_display.isoformat(),
            "end_exclusive": cycle_end_exclusive.isoformat(),
            "label": f"{cycle_start.isoformat()} → {cycle_end_display.isoformat()}",
            "closing_day": 5,
            "rolls_on_day": 6,
        },
        "expense_cycle": {
            "start": expense_start.isoformat(),
            "end": expense_end_display.isoformat(),
            "end_exclusive": expense_end_exclusive.isoformat(),
            "label": f"{expense_start.isoformat()} → {expense_end_display.isoformat()}",
            "cut_day": 21,
            "closed": expense_closed,
        },
        "income": {
            "fixed_expected": round(base_net, 2),
            "extra_expected": round(extra_expected, 2),
            "expected_total": round(expected_total, 2),
            "received_from_transactions": round(income_received_total, 2),
            "items": extra_items,
        },
        "expenses": {
            "current_period": round(total_outflow, 2),
            "spending_only": round(expenses_total, 2),
            "debt_payments": round(debt_payments_total, 2),
            "items": expenses + debt_payments,
            "transaction_count": len(expenses),
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
            "formula": "Income 5→5 - statement expenses 21→21 - debt payments - critical reserves",
        },
        "transactions": expenses + debt_payments + income_transactions + loan_transactions,
        "payroll_projection": salary_projection,
        "debug": {
            "expense_rows": len(expenses),
            "expense_sum": round(expenses_total, 2),
            "debt_payment_rows": len(debt_payments),
            "debt_payment_sum": round(debt_payments_total, 2),
            "income_rows": len(income_transactions),
            "income_sum": round(income_received_total, 2),
        },
        "user_id": user_id,
        "workspace_id": workspace_id,
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
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM employment_profile WHERE workspace_id = %s",
            (workspace_id,)
        )

        cursor = conn.execute(
            """
            INSERT INTO employment_profile (
                hourly_rate,
                regular_hours_per_week,
                overtime_multiplier,
                holiday_multiplier,
                user_id,
                workspace_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                hourly_rate,
                regular_hours_per_week,
                overtime_multiplier,
                holiday_multiplier,
                user_id,
                workspace_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "hourly_rate": hourly_rate,
        "regular_hours_per_week": regular_hours_per_week,
        "overtime_multiplier": overtime_multiplier,
        "holiday_multiplier": holiday_multiplier,
        "user_id": user_id,
        "workspace_id": workspace_id
    }


def get_employment_profile():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        profile = conn.execute(
            """
            SELECT id, hourly_rate, regular_hours_per_week, overtime_multiplier, holiday_multiplier, user_id, workspace_id, created_at
            FROM employment_profile
            WHERE workspace_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (workspace_id,)
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
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO payroll_deductions (
                name,
                deduction_type,
                amount,
                frequency,
                user_id,
                workspace_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (name, deduction_type, amount, frequency, user_id, workspace_id)
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "name": name,
        "deduction_type": deduction_type,
        "amount": amount,
        "frequency": frequency,
        "user_id": user_id,
        "workspace_id": workspace_id
    }


def get_payroll_deductions():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, deduction_type, amount, frequency, user_id, workspace_id, created_at
            FROM payroll_deductions
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
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
    workspace_id = get_current_workspace_id()

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
                workspace_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                event_type,
                hours,
                multiplier,
                amount,
                description,
                user_id,
                workspace_id
            )
        )

        conn.commit()

    return {
        "id": cursor.lastrowid,
        "event_type": event_type,
        "hours": hours,
        "multiplier": multiplier,
        "amount": amount,
        "description": description,
        "workspace_id": workspace_id
    }


def get_payroll_events():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, event_type, hours, multiplier, amount, description, user_id, workspace_id, created_at
            FROM payroll_events
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
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
    workspace_id = get_current_workspace_id()
    profile = get_employment_profile()
    start_month, end_month = _current_month_bounds_sql()

    with get_connection() as conn:
        deductions = [dict(row) for row in conn.execute(
            """
            SELECT name, deduction_type, amount, frequency
            FROM payroll_deductions
            WHERE workspace_id = %s
            """,
            (workspace_id,),
        ).fetchall()]

        payroll_events = [dict(row) for row in conn.execute(
            """
            SELECT event_type, hours, multiplier, amount, description, created_at
            FROM payroll_events
            WHERE workspace_id = %s
              AND created_at >= %s::date
              AND created_at < %s::date
            ORDER BY created_at ASC
            """,
            (workspace_id, start_month, end_month),
        ).fetchall()]

        current_bonuses = [dict(row) for row in conn.execute(
            """
            SELECT amount, description, created_at
            FROM bonuses
            WHERE workspace_id = %s
              AND created_at >= %s::date
              AND created_at < %s::date
            ORDER BY created_at ASC
            """,
            (workspace_id, start_month, end_month),
        ).fetchall()]

    base_salary_net = _latest_base_salary(workspace_id)

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
    workspace_id = get_current_workspace_id()

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
            AND workspace_id = %s
            """,
            (expense_id, workspace_id)
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
            AND workspace_id = %s
            """,
            (expense_id, workspace_id)
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
    workspace_id = get_current_workspace_id()
    category = normalize_category(category, "expense")
    if not expense_type or expense_type == "variable":
        expense_type = expense_type_for_category(category)

    with get_connection() as conn:
        expense = conn.execute(
            """
            SELECT id
            FROM expenses
            WHERE id = %s
            AND workspace_id = %s
            """,
            (expense_id, workspace_id)
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
            AND workspace_id = %s
            """,
            (
                category,
                amount,
                expense_type,
                description,
                expense_id,
                workspace_id
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
        "workspace_id": workspace_id,
        "status": "OK"
    }

def delete_debt(debt_id: int):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

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
            AND workspace_id = %s
            """,
            (debt_id, workspace_id)
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
              AND workspace_id = %s
            """,
            (debt_id, workspace_id)
        )

        conn.execute(
            """
            DELETE FROM debts
            WHERE id = %s
            AND workspace_id = %s
            """,
            (debt_id, workspace_id)
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
    interest_method: str = "monthly",
    fixed_fee_amount: float = 0,
):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, installments_paid, start_date, first_payment_date
            FROM debts
            WHERE id = %s
            AND workspace_id = %s
            """,
            (debt_id, workspace_id)
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
                interest_method = %s,
                fixed_fee_amount = %s,
                updated_at = NOW()
            WHERE id = %s
            AND workspace_id = %s
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
                str(interest_method or "monthly"),
                max(_as_float(fixed_fee_amount), 0),
                debt_id,
                workspace_id
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
        "interest_method": str(interest_method or "monthly"),
        "fixed_fee_amount": max(_as_float(fixed_fee_amount), 0),
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
    """Apply a pure extraordinary payment directly to principal."""
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    amount = max(_as_float(amount), 0)
    if amount <= 0:
        return {"message": "El abono debe ser mayor que cero.", "status": "ERROR"}

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, name, remaining_amount, monthly_payment, installments_paid
            FROM debts WHERE id = %s AND workspace_id = %s
            """, (debt_id, workspace_id)
        ).fetchone()
        if not debt:
            return {"message": "Deuda no encontrada o no pertenece al usuario actual.", "status": "ERROR"}

        previous_balance = _as_float(debt["remaining_amount"])
        previous_payment = _as_float(debt["monthly_payment"])
        principal = min(amount, previous_balance)
        final_balance = max(previous_balance - principal, 0)
        final_payment = _as_float(new_monthly_payment) if new_monthly_payment is not None else previous_payment

        conn.execute(
            """UPDATE debts
               SET remaining_amount = %s, monthly_payment = %s,
                   auto_update_monthly = CASE WHEN %s <= 0 THEN FALSE ELSE auto_update_monthly END,
                   next_payment_date = CASE WHEN %s <= 0 THEN NULL ELSE next_payment_date END,
                   updated_at = NOW()
               WHERE id = %s AND workspace_id = %s""",
            (final_balance, final_payment, final_balance, final_balance, debt_id, workspace_id),
        )
        cursor = conn.execute(
            """
            INSERT INTO debt_payments (
                user_id, workspace_id, debt_id, payment_type, amount, principal_amount, interest_amount,
                fee_amount, extra_principal_amount, previous_remaining_amount, new_remaining_amount,
                previous_monthly_payment, new_monthly_payment, description, payment_date,
                installment_number, source, created_at
            ) VALUES (%s, %s, %s, 'extra_payment', %s, %s, 0, 0, %s, %s, %s, %s, %s, %s, %s, %s, 'manual_extra', NOW())
            """,
            (user_id, workspace_id, debt_id, principal, principal, principal, previous_balance, final_balance,
             previous_payment, final_payment, description or "Abono extraordinario a principal",
             date.today().isoformat(), int(debt.get("installments_paid") or 0)),
        )
        conn.execute(
            """INSERT INTO transactions (user_id, workspace_id, transaction_date, description, amount, transaction_type,
                                      category, account, source, notes, created_at)
               VALUES (%s, %s, %s, %s, %s, 'debt_payment', %s, NULL, 'manual_debt_extra', %s, NOW())""",
            (user_id, workspace_id, date.today().isoformat(), f"Abono extra {debt['name']}", principal, debt['name'],
             f"debt_id:{debt_id};extra_payment_id:{cursor.lastrowid}"),
        )
        conn.commit()

    return {
        "message": "Abono extraordinario aplicado 100% a principal.",
        "payment_id": cursor.lastrowid, "debt_id": debt_id, "debt_name": debt["name"],
        "payment_amount": round(principal, 2), "principal_amount": round(principal, 2),
        "extra_principal_amount": round(principal, 2), "interest_amount": 0, "fee_amount": 0,
        "previous_remaining_amount": round(previous_balance, 2),
        "new_remaining_amount": round(final_balance, 2), "status": "OK"
    }

def get_debt_by_name(name: str):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

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
            AND workspace_id = %s
            LIMIT 1
            """,
            (search, workspace_id)
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
    payment_date: str | None = None,
    new_remaining_amount: float | None = None,
    new_monthly_payment: float | None = None,
    description: str = ""
):
    """Register a real payment and calculate interest/principal automatically.

    Any amount above the scheduled monthly payment is applied entirely to principal.
    `new_remaining_amount` is kept only for backwards API compatibility and is ignored
    when the amortization engine has the required debt data.
    """
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    amount = max(_as_float(amount), 0)
    paid_on = _parse_date(payment_date) or date.today()
    if amount <= 0:
        return {"message": "El pago debe ser mayor que cero.", "status": "ERROR"}

    with get_connection() as conn:
        debt = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount, monthly_payment,
                   interest_rate, term_months, payment_day, user_id, installments_paid,
                   last_payment_date, first_payment_date, interest_method, fixed_fee_amount
            FROM debts WHERE id = %s AND workspace_id = %s
            """, (debt_id, workspace_id)
        ).fetchone()
        if not debt:
            return {"message": "Deuda no encontrada o no pertenece al usuario actual.", "status": "ERROR"}

        previous_balance = _as_float(debt["remaining_amount"])
        scheduled = _normalize_debt_payment_value(debt["monthly_payment"], previous_balance)

        # If the calendar engine already applied this installment automatically,
        # registering the real payment must NOT charge the base installment twice.
        # Only the amount above the scheduled payment is an extraordinary principal payment.
        latest_auto = conn.execute(
            """
            SELECT id, amount, principal_amount, interest_amount, fee_amount,
                   new_remaining_amount, payment_date, installment_number
            FROM debt_payments
            WHERE workspace_id = %s AND debt_id = %s
              AND payment_type = 'monthly_payment' AND source = 'auto_schedule'
            ORDER BY installment_number DESC, payment_date DESC
            LIMIT 1
            """,
            (workspace_id, debt_id),
        ).fetchone()
        if latest_auto and int(latest_auto.get("installment_number") or 0) == int(debt.get("installments_paid") or 0):
            auto_date = _parse_date(latest_auto.get("payment_date"))
            if auto_date and paid_on >= auto_date and (paid_on.year, paid_on.month) == (auto_date.year, auto_date.month):
                extra_cash = round(max(amount - scheduled, 0), 2)
                if extra_cash <= 0:
                    return {
                        "message": "La cuota base ya fue aplicada automáticamente por calendario; no se duplicó el pago.",
                        "payment_amount": round(_as_float(latest_auto.get("amount")), 2),
                        "scheduled_payment": round(scheduled, 2),
                        "interest_amount": round(_as_float(latest_auto.get("interest_amount")), 2),
                        "fee_amount": round(_as_float(latest_auto.get("fee_amount")), 2),
                        "principal_amount": round(_as_float(latest_auto.get("principal_amount")), 2),
                        "extra_principal_amount": 0,
                        "new_remaining_amount": round(previous_balance, 2),
                        "installment_number": int(latest_auto.get("installment_number") or 0),
                        "status": "OK",
                    }

                extra_principal = min(extra_cash, previous_balance)
                final_balance = round(max(previous_balance - extra_principal, 0), 2)
                conn.execute(
                    """UPDATE debts SET remaining_amount = %s,
                           auto_update_monthly = CASE WHEN %s <= 0 THEN FALSE ELSE auto_update_monthly END,
                           next_payment_date = CASE WHEN %s <= 0 THEN NULL ELSE next_payment_date END,
                           updated_at = NOW()
                       WHERE id = %s AND workspace_id = %s""",
                    (final_balance, final_balance, final_balance, debt_id, workspace_id),
                )
                cursor = conn.execute(
                    """
                    INSERT INTO debt_payments (
                        user_id, workspace_id, debt_id, payment_type, amount, principal_amount, interest_amount,
                        fee_amount, extra_principal_amount, previous_remaining_amount, new_remaining_amount,
                        previous_monthly_payment, new_monthly_payment, description, payment_date,
                        installment_number, source, created_at
                    ) VALUES (%s, %s, %s, 'extra_payment', %s, %s, 0, 0, %s, %s, %s, %s, %s, %s, %s, %s, 'manual_extra_after_auto', NOW())
                    """,
                    (user_id, workspace_id, debt_id, extra_principal, extra_principal, extra_principal, previous_balance,
                     final_balance, scheduled, scheduled, description or "Excedente de cuota a principal",
                     paid_on.isoformat(), int(latest_auto.get("installment_number") or 0)),
                )
                conn.execute(
                    """INSERT INTO transactions (user_id, workspace_id, transaction_date, description, amount, transaction_type,
                                              category, account, source, notes, created_at)
                       VALUES (%s, %s, %s, %s, %s, 'debt_payment', %s, NULL, 'manual_debt_extra', %s, NOW())""",
                    (user_id, workspace_id, paid_on.isoformat(), f"Abono extra {debt['name']}", extra_principal, debt['name'],
                     f"debt_id:{debt_id};extra_payment_id:{cursor.lastrowid}"),
                )
                conn.commit()
                return {
                    "message": "La cuota base ya estaba aplicada; el excedente fue 100% a principal.",
                    "payment_id": cursor.lastrowid, "debt_id": debt_id, "debt_name": debt["name"],
                    "payment_amount": round(amount, 2), "scheduled_payment": round(scheduled, 2),
                    "interest_amount": round(_as_float(latest_auto.get("interest_amount")), 2),
                    "fee_amount": round(_as_float(latest_auto.get("fee_amount")), 2),
                    "principal_amount": round(_as_float(latest_auto.get("principal_amount")) + extra_principal, 2),
                    "extra_principal_amount": round(extra_principal, 2),
                    "previous_remaining_amount": round(previous_balance, 2),
                    "new_remaining_amount": final_balance,
                    "installment_number": int(latest_auto.get("installment_number") or 0),
                    "status": "OK",
                }
        previous_monthly = scheduled
        final_monthly = _as_float(new_monthly_payment) if new_monthly_payment is not None else scheduled
        last_paid = _parse_date(debt.get("last_payment_date"))
        if not last_paid:
            first_due = _parse_date(debt.get("first_payment_date"))
            last_paid = _add_months(first_due, -1, debt.get("payment_day") or first_due.day) if first_due else paid_on - timedelta(days=30)

        actual_payment, principal, interest, fee, extra_principal = _payment_breakdown_with_extra(
            previous_balance, amount, scheduled, debt.get("interest_rate"),
            debt.get("fixed_fee_amount"), debt.get("interest_method") or "monthly",
            last_paid, paid_on,
        )
        if principal <= 0 and previous_balance > 0:
            return {
                "message": "El pago no cubre intereses/cargos suficientes para reducir principal.",
                "interest_amount": interest, "fee_amount": fee, "status": "ERROR"
            }

        final_balance = round(max(previous_balance - principal, 0), 2)
        installment_number = int(debt.get("installments_paid") or 0) + 1
        term = int(debt.get("term_months") or 0)
        finished = final_balance <= 0 or (term > 0 and installment_number >= term)
        next_due = None if finished else _add_months(paid_on, 1, debt.get("payment_day") or paid_on.day)

        conn.execute(
            """
            UPDATE debts SET remaining_amount = %s, monthly_payment = %s,
                installments_paid = %s, last_payment_date = %s, next_payment_date = %s,
                auto_update_monthly = CASE WHEN %s THEN FALSE ELSE auto_update_monthly END, updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            """,
            (final_balance, final_monthly, installment_number, paid_on.isoformat(),
             next_due.isoformat() if next_due else None, bool(finished), debt_id, workspace_id),
        )

        cursor = conn.execute(
            """
            INSERT INTO debt_payments (
                user_id, workspace_id, debt_id, payment_type, amount, principal_amount, interest_amount,
                fee_amount, extra_principal_amount, previous_remaining_amount, new_remaining_amount,
                previous_monthly_payment, new_monthly_payment, description, payment_date,
                installment_number, source, created_at
            ) VALUES (%s, %s, %s, 'monthly_payment', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'manual', NOW())
            """,
            (user_id, workspace_id, debt_id, actual_payment, principal, interest, fee, extra_principal,
             previous_balance, final_balance, previous_monthly, final_monthly,
             description or f"Pago cuota {installment_number}", paid_on.isoformat(), installment_number),
        )

        note = f"debt_id:{debt_id};payment_id:{cursor.lastrowid}"
        conn.execute(
            """
            INSERT INTO transactions (user_id, workspace_id, transaction_date, description, amount, transaction_type,
                                      category, account, source, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, 'debt_payment', %s, NULL, 'manual_debt_payment', %s, NOW())
            """,
            (user_id, workspace_id, paid_on.isoformat(), f"Pago {debt['name']}", actual_payment, debt['name'], note),
        )
        conn.commit()

    return {
        "message": "Pago registrado y amortización calculada correctamente.",
        "payment_id": cursor.lastrowid, "debt_id": debt_id, "debt_name": debt["name"],
        "payment_amount": round(actual_payment, 2), "scheduled_payment": round(scheduled, 2),
        "interest_amount": round(interest, 2), "fee_amount": round(fee, 2),
        "principal_amount": round(principal, 2), "extra_principal_amount": round(extra_principal, 2),
        "previous_remaining_amount": round(previous_balance, 2), "new_remaining_amount": final_balance,
        "installment_number": installment_number, "next_payment_date": next_due.isoformat() if next_due else None,
        "status": "OK"
    }

def get_debt_payments(debt_id: int | None = None):
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        if debt_id:
            rows = conn.execute(
                """
                SELECT id, user_id, workspace_id, debt_id, payment_type, amount, previous_remaining_amount,
                       new_remaining_amount, previous_monthly_payment,
                       new_monthly_payment, principal_amount, interest_amount, fee_amount, extra_principal_amount,
                       description, payment_date, installment_number, source, created_at
                FROM debt_payments
                WHERE debt_id = %s
                AND workspace_id = %s
                ORDER BY id DESC
                """,
                (debt_id, workspace_id)
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, user_id, workspace_id, debt_id, payment_type, amount, previous_remaining_amount,
                       new_remaining_amount, previous_monthly_payment,
                       new_monthly_payment, principal_amount, interest_amount, fee_amount, extra_principal_amount,
                       description, payment_date, installment_number, source, created_at
                FROM debt_payments
                WHERE workspace_id = %s
                ORDER BY id DESC
                """,
                (workspace_id,)
            ).fetchall()

    return [dict(row) for row in rows]

def get_net_worth_report():
    """Reporte de patrimonio tolerante a listas vacías y NUMERIC de PostgreSQL."""
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        savings = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id, workspace_id
            FROM savings
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
        ).fetchall()

        investments = conn.execute(
            """
            SELECT id, name, amount, created_at, user_id, workspace_id
            FROM investments
            WHERE workspace_id = %s
            ORDER BY id DESC
            """,
            (workspace_id,)
        ).fetchall()

        debts = conn.execute(
            """
            SELECT id, name, debt_type, total_amount, remaining_amount,
                   monthly_payment, interest_rate, term_months,
                   payment_day, created_at, user_id, workspace_id
            FROM debts
            WHERE workspace_id = %s
            ORDER BY remaining_amount DESC
            """,
            (workspace_id,)
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
        "workspace_id": workspace_id,
    }

def get_user_status():
    """Estado general del usuario, funcionando aunque la base esté vacía."""
    summary = get_financial_summary()
    net_worth = get_net_worth_report()

    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        goals = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date,
                   priority, status, created_at, user_id
            FROM financial_goals
            WHERE status = 'active'
            AND workspace_id = %s
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
            (workspace_id,)
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
        "workspace_id": workspace_id,
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
