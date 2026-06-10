from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _date_expr(column: str = "transaction_date") -> str:
    raw = f"NULLIF(BTRIM({column}::text), '')"
    return (
        "CASE "
        f"WHEN {raw} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' "
        f"THEN SUBSTRING({raw} FROM 1 FOR 10)::date "
        "ELSE NULL END"
    )


def _month_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = today.replace(day=1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1)
    else:
        end = date(today.year, today.month + 1, 1)
    return start, end




def _ensure_receivable_tables(conn) -> None:
    """Create/upgrade receivable tables used by manual and automatic IOU tracking.

    Automatic receivables are generated from confirmed additional-card purchases
    (for example Emily's BAC additional cards). Manual receivables can still be
    created from the UI or chat.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receivables (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 1,
            person_name TEXT NOT NULL,
            original_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            paid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            pending_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            notes TEXT,
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_key TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute("ALTER TABLE receivables ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'manual'")
    conn.execute("ALTER TABLE receivables ADD COLUMN IF NOT EXISTS source_key TEXT")
    conn.execute("ALTER TABLE receivables ADD COLUMN IF NOT EXISTS notes TEXT")
    conn.execute("ALTER TABLE receivables ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    conn.execute("ALTER TABLE receivables ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receivable_payments (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 1,
            receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
            amount NUMERIC(14,2) NOT NULL,
            source_transaction_id BIGINT,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivables_user_status ON receivables(user_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivables_source_key ON receivables(user_id, source_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivable_payments_receivable ON receivable_payments(user_id, receivable_id)")


def _ensure_card_aliases(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS card_aliases (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 1,
            card_last4 TEXT NOT NULL,
            owner_label TEXT NOT NULL,
            relationship TEXT,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _fetch_additional_card_totals(conn, user_id: int) -> list[dict[str, Any]]:
    """Return what each additional-card owner owes from accepted card expenses.

    The canonical source of additional-card ownership is card_aliases + the
    parsed email candidates, because the final transactions table intentionally
    does not store card_owner/card_last4.  Earlier versions required a candidate
    to be linked to a transaction_id and this made receivables fall back to ₡0
    even while the Additional Cards page correctly showed Emily's purchases.

    Count only accepted, non-duplicate card expenses from additional cards.  If
    the transaction row exists we prefer t.amount; otherwise we fall back to the
    candidate amount so the receivable can still be calculated during review or
    after partial imports.
    """
    _ensure_card_aliases(conn)
    rows = conn.execute(
        """
        SELECT
            a.owner_label AS person_name,
            COALESCE(SUM(COALESCE(t.amount, c.amount)), 0) AS total_amount,
            COUNT(*) AS movement_count,
            ARRAY_AGG(DISTINCT a.card_last4 ORDER BY a.card_last4) AS cards
        FROM card_aliases a
        JOIN email_transaction_candidates c
          ON c.user_id = a.user_id
         AND c.card_last4 = a.card_last4
        LEFT JOIN transactions t
          ON t.user_id = c.user_id
         AND t.id = c.transaction_id
        WHERE a.user_id = %s
          AND COALESCE(a.is_primary, FALSE) = FALSE
          AND LOWER(TRIM(a.owner_label)) NOT IN ('kenneth', 'kenneth andres')
          AND COALESCE(c.transaction_type, t.transaction_type, '') = 'expense'
          AND COALESCE(c.status, '') IN ('confirmed', 'auto_saved', 'imported')
          AND COALESCE(c.status, '') NOT IN ('duplicate', 'rejected')
          AND COALESCE(COALESCE(t.amount, c.amount), 0) > 0
        GROUP BY a.owner_label
        ORDER BY a.owner_label
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _sync_auto_additional_card_receivables(conn, user_id: int) -> None:
    """Upsert automatic receivables from additional-card spending.

    If Emily made ₡137.731 in confirmed additional-card purchases, an automatic
    receivable is maintained for Emily. Existing payments are preserved and only
    the original/pending amounts are recalculated.
    """
    _ensure_receivable_tables(conn)
    totals = _fetch_additional_card_totals(conn, user_id)
    seen_keys: set[str] = set()

    for row in totals:
        person = str(row.get("person_name") or "").strip()
        if not person:
            continue
        source_key = f"additional_cards:{person.lower()}"
        seen_keys.add(source_key)
        original = round(max(_as_float(row.get("total_amount")), 0.0), 2)
        notes = (
            f"AUTO_ADDITIONAL_CARD owner={person}; "
            f"cards={','.join(row.get('cards') or [])}; "
            f"movements={int(row.get('movement_count') or 0)}"
        )
        existing = conn.execute(
            """
            SELECT id, paid_amount
            FROM receivables
            WHERE user_id = %s AND source_key = %s
            LIMIT 1
            """,
            (user_id, source_key),
        ).fetchone()
        paid = _as_float(existing["paid_amount"]) if existing else 0.0
        pending = round(max(original - paid, 0.0), 2)
        status = "completed" if pending <= 0.01 and original > 0 else "partial" if paid > 0 else "pending"

        if existing:
            conn.execute(
                """
                UPDATE receivables
                SET person_name = %s,
                    original_amount = %s,
                    pending_amount = %s,
                    status = %s,
                    source_type = 'additional_card_auto',
                    notes = %s,
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (person, original, pending, status, notes, existing["id"], user_id),
            )
        elif original > 0:
            conn.execute(
                """
                INSERT INTO receivables (
                    user_id, person_name, original_amount, paid_amount,
                    pending_amount, status, notes, source_type, source_key
                )
                VALUES (%s, %s, %s, 0, %s, %s, %s, 'additional_card_auto', %s)
                """,
                (user_id, person, original, pending, status, notes, source_key),
            )

    # If an owner no longer has confirmed purchases, keep the row but set the
    # original to zero; manual payments/history remain intact.
    stale_rows = conn.execute(
        """
        SELECT id, paid_amount
        FROM receivables
        WHERE user_id = %s
          AND source_type = 'additional_card_auto'
          AND source_key IS NOT NULL
        """,
        (user_id,),
    ).fetchall()
    for stale in stale_rows:
        key = str(stale.get("source_key") or "")
        if key in seen_keys:
            continue
        paid = _as_float(stale.get("paid_amount"))
        conn.execute(
            """
            UPDATE receivables
            SET original_amount = 0,
                pending_amount = 0,
                status = 'completed',
                notes = COALESCE(notes, '') || ' | Sin compras adicionales confirmadas actualmente.',
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (stale["id"], user_id),
        )

def _fetch_active_goals(user_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date, priority, status, created_at
            FROM financial_goals
            WHERE user_id = %s
              AND COALESCE(status, 'active') = 'active'
            ORDER BY
              CASE LOWER(priority)
                WHEN 'critical' THEN 1
                WHEN 'critica' THEN 1
                WHEN 'crítica' THEN 1
                WHEN 'high' THEN 2
                WHEN 'alta' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'media' THEN 3
                ELSE 4
              END,
              target_date ASC NULLS LAST,
              id ASC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _months_until(target_date: Any) -> int:
    if not target_date:
        return 12
    try:
        target = datetime.fromisoformat(str(target_date)[:10]).date()
    except Exception:
        return 12
    today = date.today()
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day > today.day:
        months += 1
    return max(months, 1)


def _priority_weight(priority: str | None) -> float:
    value = (priority or "medium").lower().strip()
    if value in {"critical", "critica", "crítica"}:
        return 1.0
    if value in {"high", "alta"}:
        return 0.75
    if value in {"medium", "media"}:
        return 0.45
    return 0.2


def calculate_goal_reserves(goals: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    total_required = 0.0
    total_weighted = 0.0
    critical_required = 0.0

    for goal in goals:
        target = _as_float(goal.get("target_amount"))
        current = _as_float(goal.get("current_amount"))
        remaining = max(target - current, 0.0)
        months = _months_until(goal.get("target_date"))
        monthly_required = remaining / months if months else remaining
        weight = _priority_weight(goal.get("priority"))
        weighted_reserve = monthly_required * weight
        total_required += monthly_required
        total_weighted += weighted_reserve
        if weight >= 1:
            critical_required += monthly_required

        items.append({
            "id": goal.get("id"),
            "name": goal.get("name"),
            "priority": goal.get("priority") or "medium",
            "target_amount": round(target, 2),
            "current_amount": round(current, 2),
            "remaining_amount": round(remaining, 2),
            "target_date": goal.get("target_date"),
            "months_left": months,
            "monthly_required": round(monthly_required, 2),
            "auto_reserve": round(weighted_reserve, 2),
        })

    return {
        "items": items,
        "monthly_required_all_goals": round(total_required, 2),
        "monthly_auto_reserve": round(total_weighted, 2),
        "critical_monthly_required": round(critical_required, 2),
    }


def get_real_availability() -> dict[str, Any]:
    """Ingreso neto - gastos fijos - deudas - metas críticas/ponderadas."""
    user_id = get_current_user_id()
    start, end = _month_bounds()
    date_sql = _date_expr("transaction_date")

    with get_connection() as conn:
        salary = conn.execute(
            "SELECT amount FROM salaries WHERE user_id = %s ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        income_extra = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS total
            FROM bonuses
            WHERE user_id = %s AND created_at >= %s::date AND created_at < %s::date
            """,
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchone()["total"]
        payroll_extra = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS total
            FROM payroll_events
            WHERE user_id = %s AND created_at >= %s::date AND created_at < %s::date
            """,
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchone()["total"]
        fixed_expenses = conn.execute(
            """
            SELECT COALESCE(SUM(expected_amount), 0) AS total
            FROM fixed_expenses
            WHERE user_id = %s AND COALESCE(is_active, true) = true
            """,
            (user_id,),
        ).fetchone()["total"]
        debt_minimums = conn.execute(
            "SELECT COALESCE(SUM(monthly_payment),0) AS total FROM debts WHERE user_id = %s",
            (user_id,),
        ).fetchone()["total"]
        current_expenses = conn.execute(
            f"""
            SELECT COALESCE(SUM(amount),0) AS total
            FROM transactions
            WHERE user_id = %s
              AND transaction_type = 'expense'
              AND {date_sql} >= %s::date
              AND {date_sql} < %s::date
            """,
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchone()["total"]

    goals = _fetch_active_goals(user_id)
    goal_reserves = calculate_goal_reserves(goals)

    net_income = _as_float(salary["amount"] if salary else 0) + _as_float(income_extra) + _as_float(payroll_extra)
    fixed = _as_float(fixed_expenses)
    debts = _as_float(debt_minimums)
    critical_goals = _as_float(goal_reserves["critical_monthly_required"])
    weighted_goals = _as_float(goal_reserves["monthly_auto_reserve"])
    goal_deduction = max(critical_goals, weighted_goals)
    available = net_income - fixed - debts - goal_deduction

    return {
        "status": "OK",
        "formula": "Ingreso Neto - Gastos Fijos - Deudas - Metas Críticas = Dinero Realmente Disponible",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "income_net": round(net_income, 2),
        "fixed_expenses": round(fixed, 2),
        "debt_minimums": round(debts, 2),
        "critical_goals_reserve": round(critical_goals, 2),
        "weighted_goals_reserve": round(weighted_goals, 2),
        "goals_reserved": round(goal_deduction, 2),
        "money_really_available": round(available, 2),
        "current_expenses_registered": round(_as_float(current_expenses), 2),
        "goal_reserves": goal_reserves,
        "alerts": [
            "Las metas críticas ya reducen la disponibilidad real."
            if critical_goals > 0 else
            "No hay metas críticas activas afectando el presupuesto."
        ],
    }


def _simulate_payoff(balance: float, monthly_payment: float, monthly_rate: float, max_months: int = 600) -> dict[str, Any]:
    balance = max(_as_float(balance), 0.0)
    payment = max(_as_float(monthly_payment), 0.0)
    rate = max(_as_float(monthly_rate), 0.0)
    if balance <= 0:
        return {"months": 0, "total_interest": 0, "total_paid": 0, "status": "PAID"}
    if payment <= 0:
        return {"months": None, "total_interest": None, "total_paid": None, "status": "NO_PAYMENT"}
    if rate > 0 and payment <= balance * rate:
        return {"months": None, "total_interest": None, "total_paid": None, "status": "PAYMENT_TOO_LOW"}
    months = 0
    interest_total = 0.0
    paid = 0.0
    while balance > 0.01 and months < max_months:
        interest = balance * rate
        principal = min(max(payment - interest, 0), balance)
        interest_total += interest
        paid += interest + principal
        balance -= principal
        months += 1
    return {
        "months": months,
        "total_interest": round(interest_total, 2),
        "total_paid": round(paid, 2),
        "status": "OK" if months < max_months else "TOO_LONG",
    }


def _monthly_rate(rate: float) -> float:
    rate = _as_float(rate)
    if rate <= 0:
        return 0.0
    return rate / 100 if rate <= 5 else (rate / 100) / 12


def get_debt_advisory(extra_cash: float | None = None) -> dict[str, Any]:
    user_id = get_current_user_id()
    availability = get_real_availability()
    surplus = _as_float(extra_cash, _as_float(availability.get("money_really_available")))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, debt_type, remaining_amount, monthly_payment, interest_rate, payment_day
            FROM debts
            WHERE user_id = %s AND remaining_amount > 0
            ORDER BY remaining_amount DESC
            """,
            (user_id,),
        ).fetchall()
    debts = [dict(row) for row in rows]
    if not debts:
        return {"status": "EMPTY", "message": "Señor, no hay deudas activas para simular.", "scenarios": []}

    scenarios = []
    for debt in debts:
        balance = _as_float(debt.get("remaining_amount"))
        minimum = _as_float(debt.get("monthly_payment"))
        rate = _monthly_rate(_as_float(debt.get("interest_rate")))
        monthly_extra = max(surplus, 0.0)
        amortization_payment = minimum + monthly_extra
        amortization = _simulate_payoff(balance, amortization_payment, rate)

        # Save-then-liquidate assumes surplus is accumulated and still pays minimums.
        reserve_rate = 0.02 / 12  # conservative high-yield placeholder; transparent, not investment advice.
        months_to_save = math.ceil(balance / monthly_extra) if monthly_extra > 0 else None
        save_interest_cost = None
        if months_to_save:
            shadow = _simulate_payoff(balance, minimum, rate, max_months=months_to_save)
            save_interest_cost = shadow.get("total_interest")

        hybrid_extra = monthly_extra * 0.5
        hybrid = _simulate_payoff(balance, minimum + hybrid_extra, rate)

        if rate >= 0.025:
            recommendation = "Señor, conviene amortizar cada mes porque el interés es demasiado alto."
            recommended = "A"
        elif months_to_save and months_to_save <= 4 and monthly_extra > minimum:
            recommendation = f"Señor, puede ahorrar {months_to_save} meses y cancelar de golpe sin ahogar el flujo."
            recommended = "B"
        else:
            recommendation = "Señor, recomiendo estrategia híbrida: mantenga cuota mínima y dirija parte del excedente a abonos."
            recommended = "C"

        scenarios.append({
            "debt": debt,
            "available_extra_cash": round(monthly_extra, 2),
            "A_monthly_amortization": {"payment": round(amortization_payment, 2), **amortization},
            "B_save_and_liquidate": {
                "monthly_saving": round(monthly_extra, 2),
                "estimated_months_to_lump_sum": months_to_save,
                "estimated_interest_while_saving": save_interest_cost,
                "assumed_monthly_yield": round(reserve_rate, 6),
                "status": "OK" if months_to_save else "NO_SURPLUS",
            },
            "C_hybrid": {"payment": round(minimum + hybrid_extra, 2), "extra_to_debt": round(hybrid_extra, 2), **hybrid},
            "recommended_scenario": recommended,
            "recommendation": recommendation,
        })

    return {
        "status": "OK",
        "availability": availability,
        "scenarios": scenarios,
        "message": scenarios[0]["recommendation"] if scenarios else "Señor, no hay escenario disponible.",
    }


def list_receivables() -> dict[str, Any]:
    user_id = get_current_user_id()
    with get_connection() as conn:
        _ensure_receivable_tables(conn)
        _sync_auto_additional_card_receivables(conn, user_id)
        conn.commit()
        rows = conn.execute(
            """
            SELECT id, person_name, original_amount, paid_amount, pending_amount,
                   status, notes, source_type, source_key, created_at, updated_at
            FROM receivables
            WHERE user_id = %s
            ORDER BY
              CASE status WHEN 'pending' THEN 1 WHEN 'partial' THEN 2 ELSE 3 END,
              CASE source_type WHEN 'additional_card_auto' THEN 1 ELSE 2 END,
              person_name ASC,
              id DESC
            """,
            (user_id,),
        ).fetchall()
        payments = conn.execute(
            """
            SELECT receivable_id, COALESCE(SUM(amount),0) AS total
            FROM receivable_payments
            WHERE user_id = %s
            GROUP BY receivable_id
            """,
            (user_id,),
        ).fetchall()
    by_id = {row["receivable_id"]: _as_float(row["total"]) for row in payments}
    items = []
    for row in rows:
        item = dict(row)
        paid = round(max(_as_float(item.get("paid_amount")), by_id.get(item.get("id"), 0)), 2)
        pending = round(max(_as_float(item.get("original_amount")) - paid, 0), 2)
        item["paid_amount"] = paid
        item["pending_amount"] = pending
        if pending <= 0.01 and _as_float(item.get("original_amount")) > 0:
            item["status"] = "completed"
        elif paid > 0:
            item["status"] = "partial"
        item["is_auto"] = item.get("source_type") == "additional_card_auto"
        items.append(item)
    return {
        "status": "OK",
        "items": items,
        "summary": {
            "total_pending": round(sum(_as_float(item.get("pending_amount")) for item in items), 2),
            "total_original": round(sum(_as_float(item.get("original_amount")) for item in items), 2),
            "total_paid": round(sum(_as_float(item.get("paid_amount")) for item in items), 2),
            "count_open": sum(1 for item in items if item.get("status") != "completed"),
            "auto_count": sum(1 for item in items if item.get("is_auto")),
        },
    }


def create_receivable(person_name: str, amount: float, notes: str = "") -> dict[str, Any]:
    user_id = get_current_user_id()
    amount = max(_as_float(amount), 0.0)
    if amount <= 0:
        return {"status": "ERROR", "message": "Monto inválido."}
    with get_connection() as conn:
        _ensure_receivable_tables(conn)
        row = conn.execute(
            """
            INSERT INTO receivables (user_id, person_name, original_amount, paid_amount, pending_amount, status, notes)
            VALUES (%s, %s, %s, 0, %s, 'pending', %s)
            RETURNING *
            """,
            (user_id, person_name, amount, amount, notes),
        ).fetchone()
        conn.commit()
    return {"status": "OK", "item": dict(row)}


def apply_receivable_payment(receivable_id: int, amount: float, source_transaction_id: int | None = None, notes: str = "") -> dict[str, Any]:
    user_id = get_current_user_id()
    amount = max(_as_float(amount), 0.0)
    with get_connection() as conn:
        _ensure_receivable_tables(conn)
        rec = conn.execute(
            "SELECT * FROM receivables WHERE id = %s AND user_id = %s FOR UPDATE",
            (receivable_id, user_id),
        ).fetchone()
        if not rec:
            return {"status": "NOT_FOUND", "message": "Cuenta por cobrar no encontrada."}
        pending = _as_float(rec["pending_amount"])
        payment = min(amount, pending)
        new_paid = _as_float(rec["paid_amount"]) + payment
        new_pending = max(_as_float(rec["original_amount"]) - new_paid, 0)
        status = "completed" if new_pending <= 0.01 else "partial"
        conn.execute(
            """
            INSERT INTO receivable_payments (user_id, receivable_id, amount, source_transaction_id, notes)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, receivable_id, payment, source_transaction_id, notes),
        )
        updated = conn.execute(
            """
            UPDATE receivables
            SET paid_amount = %s, pending_amount = %s, status = %s, updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (new_paid, new_pending, status, receivable_id, user_id),
        ).fetchone()
        conn.commit()
    return {"status": "OK", "item": dict(updated), "applied_amount": round(payment, 2)}


def list_account_balances() -> dict[str, Any]:
    user_id = get_current_user_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, account_name, bank_name, account_last4, currency, current_balance, is_active, updated_at
            FROM account_balances
            WHERE user_id = %s AND COALESCE(is_active, true) = true
            ORDER BY bank_name, account_name
            """,
            (user_id,),
        ).fetchall()
    items = [dict(row) for row in rows]
    return {"status": "OK", "items": items, "total_real_balance": round(sum(_as_float(i.get("current_balance")) for i in items), 2)}


def upsert_account_balance(account_name: str, current_balance: float, bank_name: str = "", account_last4: str = "", currency: str = "CRC") -> dict[str, Any]:
    user_id = get_current_user_id()
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id FROM account_balances
            WHERE user_id = %s AND LOWER(account_name) = LOWER(%s) AND COALESCE(account_last4,'') = COALESCE(%s,'')
            LIMIT 1
            """,
            (user_id, account_name, account_last4),
        ).fetchone()
        if existing:
            row = conn.execute(
                """
                UPDATE account_balances
                SET bank_name = %s, currency = %s, current_balance = %s, is_active = true, updated_at = NOW()
                WHERE id = %s AND user_id = %s
                RETURNING *
                """,
                (bank_name, currency, current_balance, existing["id"], user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO account_balances (user_id, account_name, bank_name, account_last4, currency, current_balance)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (user_id, account_name, bank_name, account_last4, currency, current_balance),
            ).fetchone()
        conn.commit()
    return {"status": "OK", "item": dict(row)}


def get_real_balance_reconciliation() -> dict[str, Any]:
    accounts = list_account_balances()
    availability = get_real_availability()
    receivables = list_receivables()
    total_real = _as_float(accounts.get("total_real_balance"))
    theoretical = _as_float(availability.get("money_really_available"))
    pending_receivables = _as_float(receivables.get("summary", {}).get("total_pending"))
    difference = total_real - theoretical
    level = "ok"
    if abs(difference) >= 50000:
        level = "high"
    elif abs(difference) >= 10000:
        level = "medium"
    return {
        "status": "OK",
        "accounts": accounts.get("items", []),
        "total_real_balance": round(total_real, 2),
        "theoretical_available": round(theoretical, 2),
        "pending_receivables": round(pending_receivables, 2),
        "difference": round(difference, 2),
        "leak_alert": {
            "level": level,
            "message": (
                "Señor, hay una discrepancia fuerte: puede haber gastos no registrados, errores de movimiento o fugas de capital."
                if level == "high" else
                "Señor, hay una diferencia por revisar entre saldo real y saldo calculado."
                if level == "medium" else
                "Señor, el saldo real está conciliado dentro del margen normal."
            ),
        },
    }


def plan_long_term_goal(description: str, estimated_total_cost: float | None = None) -> dict[str, Any]:
    availability = get_real_availability()
    monthly_available = max(_as_float(availability.get("money_really_available")), 0.0)
    text = (description or "").lower()
    if estimated_total_cost is None:
        # Conservative defaults for international event travel. Transparent placeholder until user confirms.
        if any(word in text for word in ["mónaco", "monaco", "f1", "formula", "fórmula"]):
            estimated_total_cost = 4_000_000
            breakdown = {"entradas": 750000, "hospedaje": 1400000, "alimentacion": 450000, "transporte": 1000000, "colchon": 400000}
        else:
            estimated_total_cost = 1_500_000
            breakdown = {"transporte": 500000, "hospedaje": 500000, "alimentacion": 300000, "colchon": 200000}
    else:
        breakdown = {"total_confirmado_por_usuario": estimated_total_cost}

    scenarios = []
    for name, ratio in [("Conservador", 0.25), ("Realista", 0.5), ("Agresivo", 0.8)]:
        monthly = monthly_available * ratio
        months = math.ceil(estimated_total_cost / monthly) if monthly > 0 else None
        target_year = date.today().year + math.ceil((months or 0) / 12) if months else None
        scenarios.append({"name": name, "monthly_saving": round(monthly, 2), "months": months, "target_year": target_year})

    viable = next((s for s in scenarios if s.get("months")), None)
    message = (
        f"Señor, con su flujo actual, el escenario {viable['name'].lower()} proyecta lograrlo en {viable['target_year']}."
        if viable else
        "Señor, con el flujo actual no puedo proyectarlo: primero hay que liberar dinero disponible."
    )
    return {
        "status": "OK",
        "description": description,
        "estimated_total_cost": round(_as_float(estimated_total_cost), 2),
        "breakdown": breakdown,
        "availability": availability,
        "scenarios": scenarios,
        "message": message,
        "note": "Costos estimados. Para precisión real, confirme entradas, fechas, ciudad, noches y aerolínea.",
    }
