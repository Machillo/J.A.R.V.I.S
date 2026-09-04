from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from backend.auth.current_user import get_current_user_id, get_current_workspace_id
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


def _card_cycle_bounds(today: date | None = None, cutoff_day: int = 21) -> tuple[date, date]:
    """Return the active BAC-style card cycle [start, end).

    The configured personal cycle closes on day 21. On/after the 21st the
    current cycle starts that same day; before it, the cycle started on the
    21st of the previous month.
    """
    today = today or date.today()
    cutoff_day = min(max(int(cutoff_day or 21), 1), 28)
    if today.day >= cutoff_day:
        start = today.replace(day=cutoff_day)
    else:
        if today.month == 1:
            start = date(today.year - 1, 12, cutoff_day)
        else:
            start = date(today.year, today.month - 1, cutoff_day)
    if start.month == 12:
        end = date(start.year + 1, 1, cutoff_day)
    else:
        end = date(start.year, start.month + 1, cutoff_day)
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
    conn.execute("ALTER TABLE receivables ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id)")
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivables_source_key ON receivables(workspace_id, source_key)")
    conn.execute("ALTER TABLE receivable_payments ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivable_payments_receivable ON receivable_payments(user_id, receivable_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivables_workspace_status ON receivables(workspace_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivable_payments_workspace_receivable ON receivable_payments(workspace_id, receivable_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receivable_entries (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 1,
            receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
            entry_type TEXT NOT NULL,
            amount NUMERIC(14,2) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_key TEXT,
            source_transaction_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute("ALTER TABLE receivable_entries ADD COLUMN IF NOT EXISTS cycle_start DATE")
    conn.execute("ALTER TABLE receivable_entries ADD COLUMN IF NOT EXISTS cycle_end DATE")
    conn.execute("ALTER TABLE receivable_entries ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE")
    conn.execute("ALTER TABLE receivable_entries ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivable_entries_workspace_account ON receivable_entries(workspace_id, receivable_id, entry_date DESC, id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivable_entries_account ON receivable_entries(user_id, receivable_id, entry_date DESC, id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receivable_entries_active_cycle ON receivable_entries(user_id, receivable_id, is_archived, cycle_start, cycle_end)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_entries_source_key ON receivable_entries(workspace_id, source_key) WHERE source_key IS NOT NULL")



def _person_key(person_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(person_name or "").strip().lower())
    return normalized.strip("-") or "persona"


def _get_or_create_person_receivable(conn, user_id: int, person_name: str) -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    clean_name = str(person_name or "").strip()
    if not clean_name:
        raise ValueError("La persona es obligatoria.")
    row = conn.execute(
        """
        SELECT *
        FROM receivables
        WHERE workspace_id = %s
          AND LOWER(TRIM(person_name)) = LOWER(TRIM(%s))
        ORDER BY CASE source_type WHEN 'additional_card_auto' THEN 1 ELSE 2 END, id ASC
        LIMIT 1
        """,
        (workspace_id, clean_name),
    ).fetchone()
    if row:
        return dict(row)
    created = conn.execute(
        """
        INSERT INTO receivables (
            user_id, workspace_id, person_name, original_amount, paid_amount, pending_amount,
            status, notes, source_type, source_key
        )
        VALUES (%s, %s, %s, 0, 0, 0, 'completed', '', 'person_account', %s)
        RETURNING *
        """,
        (user_id, workspace_id, clean_name, f"person:{_person_key(clean_name)}"),
    ).fetchone()
    return dict(created)


def _backfill_receivable_entries(conn, user_id: int) -> None:
    workspace_id = get_current_workspace_id()
    """Move legacy manual balances/payments into the person ledger idempotently."""
    legacy_rows = conn.execute(
        """
        SELECT id, source_type, original_amount, person_name, notes, created_at
        FROM receivables
        WHERE workspace_id = %s
          AND source_type = 'manual'
          AND COALESCE(original_amount, 0) > 0
        """,
        (workspace_id,),
    ).fetchall()
    for row in legacy_rows:
        conn.execute(
            """
            INSERT INTO receivable_entries (
                user_id, workspace_id, receivable_id, entry_type, amount, description,
                entry_date, source_type, source_key
            )
            VALUES (%s, %s, %s, 'charge', %s, %s, %s, 'legacy', %s)
            ON CONFLICT DO NOTHING
            """,
            (
                user_id,
                workspace_id,
                row["id"],
                row["original_amount"],
                row.get("notes") or f"Saldo inicial de {row.get('person_name') or 'persona'}",
                str(row.get("created_at") or date.today())[:10],
                f"legacy_receivable:{row['id']}",
            ),
        )
    payment_rows = conn.execute(
        """
        SELECT id, receivable_id, amount, source_transaction_id, notes, created_at
        FROM receivable_payments
        WHERE workspace_id = %s
        """,
        (workspace_id,),
    ).fetchall()
    for row in payment_rows:
        conn.execute(
            """
            INSERT INTO receivable_entries (
                user_id, workspace_id, receivable_id, entry_type, amount, description,
                entry_date, source_type, source_key, source_transaction_id
            )
            SELECT %s, %s, %s, 'payment', %s, %s, %s, 'legacy_payment', %s, %s
            WHERE NOT EXISTS (
                SELECT 1
                FROM receivable_entries existing
                WHERE existing.workspace_id = %s
                  AND (
                        existing.source_key = %s
                     OR (%s IS NOT NULL AND existing.source_transaction_id = %s)
                  )
            )
            ON CONFLICT DO NOTHING
            """,
            (
                user_id,
                workspace_id,
                row["receivable_id"],
                row["amount"],
                row.get("notes") or "Pago registrado",
                str(row.get("created_at") or date.today())[:10],
                f"legacy_receivable_payment:{row['id']}",
                row.get("source_transaction_id"),
                workspace_id,
                f"legacy_receivable_payment:{row['id']}",
                row.get("source_transaction_id"),
                row.get("source_transaction_id"),
            ),
        )


def _recalculate_receivable(conn, user_id: int, receivable_id: int) -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    totals = conn.execute(
        """
        SELECT
            COALESCE(SUM(amount) FILTER (WHERE entry_type = 'charge'), 0) AS charged,
            COALESCE(SUM(amount) FILTER (WHERE entry_type = 'payment'), 0) AS paid
        FROM receivable_entries
        WHERE workspace_id = %s AND receivable_id = %s
          AND COALESCE(is_archived, FALSE) = FALSE
        """,
        (workspace_id, receivable_id),
    ).fetchone()
    charged = round(max(_as_float(totals.get("charged")), 0.0), 2)
    paid = round(max(_as_float(totals.get("paid")), 0.0), 2)
    pending = round(charged - paid, 2)
    status = "credit" if pending < -0.01 else "completed" if abs(pending) <= 0.01 else "partial" if paid > 0 else "pending"
    updated = conn.execute(
        """
        UPDATE receivables
        SET original_amount = %s,
            paid_amount = %s,
            pending_amount = %s,
            status = %s,
            updated_at = NOW()
        WHERE id = %s AND workspace_id = %s
        RETURNING *
        """,
        (charged, paid, pending, status, receivable_id, workspace_id),
    ).fetchone()
    return dict(updated)

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


def _fetch_additional_card_totals(
    conn, workspace_id: str, cycle_start: date, cycle_end: date
) -> list[dict[str, Any]]:
    """Return additional-card spending only for the active card cycle.

    Historical purchases stay in prior cycles and are carried only when an
    unpaid balance remains. This prevents old payments from cancelling a new
    manual charge entered this month.
    """
    _ensure_card_aliases(conn)
    rows = conn.execute(
        """
        WITH additional_aliases AS (
            SELECT workspace_id, card_last4, owner_label
            FROM card_aliases
            WHERE workspace_id = %s
              AND COALESCE(is_primary, FALSE) = FALSE
              AND LOWER(TRIM(owner_label)) NOT IN ('kenneth', 'kenneth andres')
        ), candidate_movements AS (
            SELECT
                COALESCE(a.owner_label, c.card_owner) AS person_name,
                COALESCE(a.card_last4, c.card_last4) AS card_last4,
                COALESCE(c.transaction_id, c.id * -1) AS movement_key,
                c.amount
            FROM email_transaction_candidates c
            LEFT JOIN additional_aliases a
              ON a.workspace_id = c.workspace_id
             AND a.card_last4 = c.card_last4
            WHERE c.workspace_id = %s
              AND c.transaction_type = 'expense'
              AND COALESCE(c.amount, 0) > 0
              AND c.transaction_date >= %s
              AND c.transaction_date < %s
              AND COALESCE(c.status, '') IN ('confirmed', 'auto_saved', 'imported')
              AND COALESCE(c.status, '') NOT IN ('duplicate', 'rejected')
              AND (
                    a.card_last4 IS NOT NULL
                 OR LOWER(TRIM(COALESCE(c.card_owner,''))) IN (
                        SELECT LOWER(TRIM(owner_label)) FROM additional_aliases
                    )
              )
        )
        SELECT
            person_name,
            COALESCE(SUM(amount), 0) AS total_amount,
            COUNT(DISTINCT movement_key) AS movement_count,
            ARRAY_AGG(DISTINCT card_last4 ORDER BY card_last4)
              FILTER (WHERE card_last4 IS NOT NULL AND card_last4 <> '') AS cards
        FROM candidate_movements
        WHERE COALESCE(person_name, '') <> ''
        GROUP BY person_name
        ORDER BY person_name
        """,
        (workspace_id, workspace_id, cycle_start, cycle_end),
    ).fetchall()
    return [dict(row) for row in rows]


def _detect_receivable_payer_from_transaction(row: dict[str, Any]) -> str | None:
    """Detect a receivable payment only from explicit payer evidence.

    A generic income must never reduce Emily/Sidey automatically.  The email
    parser or the user must leave a clear payer trace in description/notes, and
    the movement must look like a SINPE/transfer/payment.  This prevents false
    matches such as the previous ₡577.20 income that was applied to Emily.
    """
    text = " ".join([
        str(row.get("description") or ""),
        str(row.get("category") or ""),
        str(row.get("account") or ""),
        str(row.get("notes") or ""),
    ]).lower()
    has_payment_context = any(token in text for token in (
        "sinpe", "sinpe movil", "sinpe móvil", "transferencia",
        "abono", "pago", "reembolso", "payer=", "remitente", "origen",
    ))
    if not has_payment_context:
        return None
    if "emily" in text or "emily andrea" in text or "emily andrea alvarado" in text:
        return "Emily"
    if "sidey" in text:
        return "Sidey"
    return None


def _sync_receivable_payments_from_income(conn, user_id: int) -> None:
    workspace_id = get_current_workspace_id()
    """Apply incoming SINPE/reimbursement payments to matching receivables.

    Example: Emily sends a SINPE Móvil payment. The transaction is income and
    notes contain payer: Emily. We record it once in receivable_payments so the
    pending balance decreases automatically without manual double entry.
    """
    rows = conn.execute(
        """
        SELECT id, transaction_date, description, amount, transaction_type, category, account, source, notes
        FROM transactions
        WHERE workspace_id = %s
          AND transaction_type IN ('income', 'reimbursement')
          AND COALESCE(amount, 0) > 0
          AND COALESCE(source, '') IN ('email_monitor', 'manual', 'jarvis')
        ORDER BY transaction_date ASC, id ASC
        """,
        (workspace_id,),
    ).fetchall()
    for raw in rows:
        tx = dict(raw)
        payer = _detect_receivable_payer_from_transaction(tx)
        if not payer:
            continue
        rec = conn.execute(
            """
            SELECT id, original_amount, paid_amount, pending_amount
            FROM receivables
            WHERE workspace_id = %s
              AND LOWER(TRIM(person_name)) = LOWER(TRIM(%s))
            ORDER BY CASE source_type WHEN 'additional_card_auto' THEN 1 ELSE 2 END, id ASC
            LIMIT 1
            """,
            (workspace_id, payer),
        ).fetchone()
        if not rec:
            continue
        already = conn.execute(
            """
            SELECT id FROM receivable_payments
            WHERE workspace_id = %s AND source_transaction_id = %s
            LIMIT 1
            """,
            (workspace_id, tx["id"]),
        ).fetchone()
        if already:
            continue
        pending = _as_float(rec.get("pending_amount"))
        payment = min(_as_float(tx.get("amount")), max(pending, 0.0))
        if payment <= 0:
            continue
        new_paid = _as_float(rec.get("paid_amount")) + payment
        new_pending = max(_as_float(rec.get("original_amount")) - new_paid, 0.0)
        status = "completed" if new_pending <= 0.01 else "partial"
        conn.execute(
            """
            INSERT INTO receivable_payments (user_id, workspace_id, receivable_id, amount, source_transaction_id, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, workspace_id, rec["id"], payment, tx["id"], f"Pago detectado automáticamente desde ingreso: {tx.get('description') or ''}"),
        )
        payment_date = tx.get("transaction_date") or date.today()
        if isinstance(payment_date, str):
            payment_date = datetime.fromisoformat(payment_date[:10]).date()
        cycle_start, cycle_end = _card_cycle_bounds(payment_date)
        conn.execute(
            """
            INSERT INTO receivable_entries (
                user_id, workspace_id, receivable_id, entry_type, amount, description,
                entry_date, source_type, source_key, source_transaction_id,
                cycle_start, cycle_end, is_archived
            )
            VALUES (%s, %s, %s, 'payment', %s, %s, %s, 'income_auto', %s, %s, %s, %s, FALSE)
            ON CONFLICT DO NOTHING
            """,
            (
                user_id,
                workspace_id,
                rec["id"],
                payment,
                f"Pago detectado: {tx.get('description') or payer}",
                payment_date,
                f"income_transaction:{tx['id']}",
                tx["id"],
                cycle_start,
                cycle_end,
            ),
        )
        _recalculate_receivable(conn, user_id, int(rec["id"]))


def _sync_auto_additional_card_receivables(conn, user_id: int) -> None:
    workspace_id = get_current_workspace_id()
    """Mirror only the active cycle's additional-card purchases."""
    _ensure_receivable_tables(conn)
    _backfill_receivable_entries(conn, user_id)
    cycle_start, cycle_end = _card_cycle_bounds()
    totals = _fetch_additional_card_totals(conn, workspace_id, cycle_start, cycle_end)

    for row in totals:
        person = str(row.get("person_name") or "").strip()
        if not person:
            continue
        account = _get_or_create_person_receivable(conn, user_id, person)
        source_key = f"additional_cards:{_person_key(person)}:{cycle_start.isoformat()}"
        amount = round(max(_as_float(row.get("total_amount")), 0.0), 2)
        description = (
            f"Compras de tarjetas adicionales del ciclo "
            f"{cycle_start.isoformat()} a {cycle_end.isoformat()} "
            f"({', '.join(row.get('cards') or []) or 'sin tarjeta'})"
        )
        if amount > 0:
            conn.execute(
                """
                INSERT INTO receivable_entries (
                    user_id, workspace_id, receivable_id, entry_type, amount, description,
                    entry_date, source_type, source_key, cycle_start, cycle_end, is_archived
                )
                VALUES (%s, %s, %s, 'charge', %s, %s, %s, 'additional_card_auto', %s, %s, %s, FALSE)
                ON CONFLICT (workspace_id, source_key) WHERE source_key IS NOT NULL
                DO UPDATE SET
                    receivable_id = EXCLUDED.receivable_id,
                    amount = EXCLUDED.amount,
                    description = EXCLUDED.description,
                    entry_date = EXCLUDED.entry_date,
                    cycle_start = EXCLUDED.cycle_start,
                    cycle_end = EXCLUDED.cycle_end,
                    is_archived = FALSE
                """,
                (
                    user_id, workspace_id, account["id"], amount, description, cycle_start,
                    source_key, cycle_start, cycle_end,
                ),
            )
            conn.execute(
                """
                UPDATE receivables
                SET source_type = CASE WHEN source_type = 'manual' THEN 'person_account' ELSE source_type END,
                    updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                """,
                (account["id"], workspace_id),
            )
            _recalculate_receivable(conn, user_id, int(account["id"]))


def _fetch_active_goals(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, target_amount, current_amount, target_date, priority, status, created_at
            FROM financial_goals
            WHERE workspace_id = %s
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
            (workspace_id,),
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
    workspace_id = get_current_workspace_id()
    start, end = _month_bounds()
    date_sql = _date_expr("transaction_date")

    try:
        from backend.finance.service import get_financial_cycle_report
        cycle = get_financial_cycle_report() or {}
    except Exception:
        cycle = {}

    goals = _fetch_active_goals(workspace_id)
    goal_reserves = calculate_goal_reserves(goals)

    net_income = _as_float(cycle.get("income", {}).get("expected_total"))
    current_expenses = _as_float(cycle.get("expenses", {}).get("current_period"))
    debt_payments = _as_float(cycle.get("debts", {}).get("payments_current_period"))
    critical_goals = _as_float(goal_reserves["critical_monthly_required"])
    weighted_goals = _as_float(goal_reserves["monthly_auto_reserve"])
    goal_deduction = max(critical_goals, weighted_goals)
    available_before_goals = net_income - current_expenses - debt_payments
    goal_allocation = min(max(available_before_goals, 0.0), goal_deduction)
    available = available_before_goals - goal_allocation

    return {
        "status": "OK",
        "formula": "Ingreso ciclo - gastos variables del ciclo - pagos de deuda - metas críticas = excedente estratégico",
        "period": cycle.get("cycle") or {"start": start.isoformat(), "end": end.isoformat()},
        "income_net": round(net_income, 2),
        "fixed_expenses": 0.0,
        "debt_minimums": round(debt_payments, 2),
        "debt_payments_current_period": round(debt_payments, 2),
        "critical_goals_reserve": round(critical_goals, 2),
        "weighted_goals_reserve": round(weighted_goals, 2),
        "goals_reserved": round(goal_allocation, 2),
        "money_really_available": round(available, 2),
        "available_before_goals": round(available_before_goals, 2),
        "current_expenses_registered": round(current_expenses, 2),
        "goal_reserves": goal_reserves,
        "alerts": [
            "Las metas críticas reciben prioridad sobre el excedente estratégico."
            if critical_goals > 0 else
            "No hay metas críticas activas afectando el excedente."
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
    workspace_id = get_current_workspace_id()
    availability = get_real_availability()
    if extra_cash is None:
        try:
            from backend.finance.service import get_financial_cycle_report
            cycle = get_financial_cycle_report() or {}
            # Use the same real cycle balance shown in Finanzas. If the cycle is
            # negative, there is no extra money for debt attack or lump-sum saving.
            surplus = _as_float(cycle.get("cashflow", {}).get("real_balance"))
        except Exception:
            surplus = _as_float(availability.get("money_really_available"))
    else:
        surplus = _as_float(extra_cash)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, debt_type, remaining_amount, monthly_payment, interest_rate, payment_day
            FROM debts
            WHERE workspace_id = %s AND remaining_amount > 0
            ORDER BY remaining_amount DESC
            """,
            (workspace_id,),
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
        baseline = _simulate_payoff(balance, minimum, rate)
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

        debt_type = str(debt.get("debt_type") or "other").lower().strip()
        if debt_type == "tasa_cero" and rate <= 0:
            recommendation = "Señor, esta deuda está a tasa cero: mantenga la cuota y no sacrifique Salvavidas o deuda con interés para adelantarla."
            recommended = "MINIMUM"
        elif rate >= 0.025:
            recommendation = "Señor, conviene amortizar cada mes porque el costo financiero es alto."
            recommended = "A"
        elif months_to_save and months_to_save <= 4 and monthly_extra > minimum:
            recommendation = f"Señor, puede acumular el excedente y tener capacidad de liquidarla en aproximadamente {months_to_save} meses."
            recommended = "B"
        else:
            recommendation = "Señor, recomiendo una estrategia híbrida: mantenga la cuota y use solo parte del excedente para acelerar."
            recommended = "C"

        baseline_months = baseline.get("months")
        a_months = amortization.get("months")
        c_months = hybrid.get("months")
        months_saved_a = max(int(baseline_months) - int(a_months), 0) if baseline_months is not None and a_months is not None else None
        months_saved_c = max(int(baseline_months) - int(c_months), 0) if baseline_months is not None and c_months is not None else None
        baseline_interest = _as_float(baseline.get("total_interest"))
        interest_saved_a = max(baseline_interest - _as_float(amortization.get("total_interest")), 0.0) if baseline.get("total_interest") is not None and amortization.get("total_interest") is not None else None
        interest_saved_c = max(baseline_interest - _as_float(hybrid.get("total_interest")), 0.0) if baseline.get("total_interest") is not None and hybrid.get("total_interest") is not None else None

        scenarios.append({
            "debt": debt,
            "available_extra_cash": round(monthly_extra, 2),
            "baseline_minimum": baseline,
            "A_monthly_amortization": {"payment": round(amortization_payment, 2), "months_saved_vs_minimum": months_saved_a, "interest_saved_vs_minimum": round(interest_saved_a, 2) if interest_saved_a is not None else None, **amortization},
            "B_save_and_liquidate": {
                "monthly_saving": round(monthly_extra, 2),
                "estimated_months_to_lump_sum": months_to_save,
                "estimated_interest_while_saving": save_interest_cost,
                "assumed_monthly_yield": round(reserve_rate, 6),
                "status": "OK" if months_to_save else "NO_SURPLUS",
            },
            "C_hybrid": {"payment": round(minimum + hybrid_extra, 2), "extra_to_debt": round(hybrid_extra, 2), "months_saved_vs_minimum": months_saved_c, "interest_saved_vs_minimum": round(interest_saved_c, 2) if interest_saved_c is not None else None, **hybrid},
            "recommended_scenario": recommended,
            "recommendation": recommendation,
        })

    if max(surplus, 0.0) <= 0:
        message = "Señor, este ciclo no tiene excedente libre; mantenga pagos mínimos y no simule abonos extra hasta corregir el flujo."
    else:
        message = scenarios[0]["recommendation"] if scenarios else "Señor, no hay escenario disponible."

    return {
        "status": "OK",
        "availability": availability,
        "available_extra_cash": round(max(surplus, 0.0), 2),
        "scenarios": scenarios,
        "message": message,
    }


def list_receivables() -> dict[str, Any]:
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    cycle_start, cycle_end = _card_cycle_bounds()
    with get_connection() as conn:
        _ensure_receivable_tables(conn)
        _backfill_receivable_entries(conn, user_id)
        _sync_auto_additional_card_receivables(conn, user_id)
        _sync_receivable_payments_from_income(conn, user_id)

        account_rows = conn.execute(
            """
            SELECT id, person_name, original_amount, paid_amount, pending_amount,
                   status, notes, source_type, source_key, created_at, updated_at
            FROM receivables
            WHERE workspace_id = %s
            ORDER BY
              CASE status WHEN 'pending' THEN 1 WHEN 'partial' THEN 2 ELSE 3 END,
              person_name ASC,
              id ASC
            """,
            (workspace_id,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        seen_people: set[str] = set()
        for raw in account_rows:
            row = dict(raw)
            person_key = str(row.get("person_name") or "").strip().lower()
            if not person_key or person_key in seen_people:
                continue
            seen_people.add(person_key)
            item = _recalculate_receivable(conn, user_id, int(row["id"]))

            cycle_totals = conn.execute(
                """
                SELECT
                    COALESCE(SUM(amount) FILTER (
                        WHERE entry_type = 'charge' AND entry_date < %s
                    ), 0) AS prior_charges,
                    COALESCE(SUM(amount) FILTER (
                        WHERE entry_type = 'payment' AND entry_date < %s
                    ), 0) AS prior_payments,
                    COALESCE(SUM(amount) FILTER (
                        WHERE entry_type = 'charge' AND entry_date >= %s AND entry_date < %s
                    ), 0) AS cycle_charges,
                    COALESCE(SUM(amount) FILTER (
                        WHERE entry_type = 'payment' AND entry_date >= %s AND entry_date < %s
                    ), 0) AS cycle_payments
                FROM receivable_entries
                WHERE workspace_id = %s AND receivable_id = %s
                  AND COALESCE(is_archived, FALSE) = FALSE
                """,
                (
                    cycle_start, cycle_start, cycle_start, cycle_end,
                    cycle_start, cycle_end, workspace_id, row["id"],
                ),
            ).fetchone()
            prior_pending = round(
                _as_float(cycle_totals.get("prior_charges"))
                - _as_float(cycle_totals.get("prior_payments")), 2
            )
            cycle_charges = max(_as_float(cycle_totals.get("cycle_charges")), 0.0)
            cycle_payments = max(_as_float(cycle_totals.get("cycle_payments")), 0.0)
            current_due = round(prior_pending + cycle_charges - cycle_payments, 2)

            history_rows = conn.execute(
                """
                SELECT id, entry_type, amount, description, entry_date,
                       source_type, source_key, source_transaction_id, created_at,
                       cycle_start, cycle_end
                FROM receivable_entries
                WHERE workspace_id = %s AND receivable_id = %s
                  AND COALESCE(is_archived, FALSE) = FALSE
                  AND (entry_date >= %s OR %s > 0)
                ORDER BY entry_date DESC, id DESC
                """,
                (workspace_id, row["id"], cycle_start, prior_pending),
            ).fetchall()
            item["history"] = [dict(entry) for entry in history_rows]
            item["is_auto"] = any(
                entry.get("source_type") == "additional_card_auto"
                for entry in item["history"]
            )
            item["cycle_start"] = cycle_start.isoformat()
            item["cycle_end"] = cycle_end.isoformat()
            item["carried_pending"] = round(prior_pending, 2)
            item["cycle_charges"] = round(cycle_charges, 2)
            item["cycle_payments"] = round(cycle_payments, 2)
            item["current_amount_due"] = round(current_due, 2)
            # Keep compatibility for existing consumers, but expose only current debt.
            item["pending_amount"] = round(current_due, 2)
            item["original_amount"] = round(prior_pending + cycle_charges, 2)
            item["paid_amount"] = round(cycle_payments, 2)
            item["status"] = "credit" if current_due < -0.01 else "completed" if abs(current_due) <= 0.01 else "partial" if cycle_payments > 0 else "pending"
            items.append(item)
        conn.commit()

    return {
        "status": "OK",
        "cycle": {"start": cycle_start.isoformat(), "end": cycle_end.isoformat()},
        "items": items,
        "summary": {
            "total_pending": round(sum(_as_float(item.get("current_amount_due")) for item in items), 2),
            "carried_pending": round(sum(_as_float(item.get("carried_pending")) for item in items), 2),
            "cycle_charges": round(sum(_as_float(item.get("cycle_charges")) for item in items), 2),
            "cycle_payments": round(sum(_as_float(item.get("cycle_payments")) for item in items), 2),
            "count_open": sum(1 for item in items if abs(_as_float(item.get("current_amount_due"))) > 0.01),
            "people_count": len(items),
        },
    }


def add_receivable_entry(
    person_name: str,
    amount: float,
    description: str,
    entry_kind: str = "purchase",
    entry_date: str | None = None,
) -> dict[str, Any]:
    """Add a manual purchase/loan/transfer owed by any person."""
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    clean_name = str(person_name or "").strip()
    clean_description = str(description or "").strip()
    clean_kind = str(entry_kind or "purchase").strip().lower()
    valid_kinds = {"purchase", "loan", "transfer", "cash", "other"}
    if clean_kind not in valid_kinds:
        clean_kind = "other"
    numeric_amount = round(max(_as_float(amount), 0.0), 2)
    if not clean_name:
        return {"status": "ERROR", "message": "La persona es obligatoria."}
    if numeric_amount <= 0:
        return {"status": "ERROR", "message": "Monto inválido."}
    try:
        safe_date = datetime.fromisoformat(str(entry_date)[:10]).date().isoformat() if entry_date else date.today().isoformat()
    except Exception:
        safe_date = date.today().isoformat()

    labels = {
        "purchase": "Compra pagada por Kenneth",
        "loan": "Dinero prestado",
        "transfer": "Transferencia prestada",
        "cash": "Efectivo prestado",
        "other": "Cuenta por cobrar manual",
    }
    final_description = clean_description or labels[clean_kind]
    with get_connection() as conn:
        _ensure_receivable_tables(conn)
        _backfill_receivable_entries(conn, user_id)
        account = _get_or_create_person_receivable(conn, user_id, clean_name)
        entry_day = datetime.fromisoformat(safe_date).date()
        cycle_start, cycle_end = _card_cycle_bounds(entry_day)
        entry = conn.execute(
            """
            INSERT INTO receivable_entries (
                user_id, workspace_id, receivable_id, entry_type, amount, description,
                entry_date, source_type, cycle_start, cycle_end, is_archived
            )
            VALUES (%s, %s, %s, 'charge', %s, %s, %s, %s, %s, %s, FALSE)
            RETURNING *
            """,
            (
                user_id, workspace_id, account["id"], numeric_amount, final_description,
                safe_date, f"manual_{clean_kind}", cycle_start, cycle_end,
            ),
        ).fetchone()
        updated = _recalculate_receivable(conn, user_id, int(account["id"]))
        conn.commit()
    return {"status": "OK", "item": updated, "entry": dict(entry)}


def update_receivable_entry(receivable_id: int, entry_id: int, amount: float | None = None, description: str | None = None, entry_date: str | None = None) -> dict[str, Any]:
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_receivable_tables(conn)
        entry = conn.execute("SELECT * FROM receivable_entries WHERE id=%s AND receivable_id=%s AND workspace_id=%s FOR UPDATE", (entry_id, receivable_id, workspace_id)).fetchone()
        if not entry:
            return {"status": "NOT_FOUND", "message": "Movimiento no encontrado."}
        new_amount = round(_as_float(amount if amount is not None else entry["amount"]), 2)
        if new_amount <= 0:
            return {"status": "ERROR", "message": "Monto inválido."}
        new_description = str(description if description is not None else entry.get("description") or "").strip()
        new_date = str(entry_date or entry.get("entry_date") or date.today())[:10]
        parsed_day = datetime.fromisoformat(new_date).date()
        cycle_start, cycle_end = _card_cycle_bounds(parsed_day)
        updated_entry = conn.execute("""
            UPDATE receivable_entries SET amount=%s, description=%s, entry_date=%s, cycle_start=%s, cycle_end=%s
            WHERE id=%s AND receivable_id=%s AND workspace_id=%s RETURNING *
        """, (new_amount, new_description, new_date, cycle_start, cycle_end, entry_id, receivable_id, workspace_id)).fetchone()
        linked_id = entry.get("source_transaction_id")
        if linked_id and entry.get("entry_type") == "payment":
            conn.execute("UPDATE transactions SET amount=%s, original_amount=%s, transaction_date=%s, notes=%s WHERE id=%s AND workspace_id=%s", (new_amount, new_amount, new_date, f"Pago corregido de cuenta por cobrar #{receivable_id}. {new_description}".strip(), linked_id, workspace_id))
            conn.execute("UPDATE receivable_payments SET amount=%s, notes=%s WHERE source_transaction_id=%s AND workspace_id=%s", (new_amount, new_description, linked_id, workspace_id))
        account = _recalculate_receivable(conn, user_id, receivable_id)
        conn.commit()
    return {"status": "OK", "item": account, "entry": dict(updated_entry)}

def create_receivable(person_name: str, amount: float, notes: str = "") -> dict[str, Any]:
    return add_receivable_entry(
        person_name=person_name,
        amount=amount,
        description=notes or "Cuenta por cobrar manual",
        entry_kind="other",
    )


def apply_receivable_payment(
    receivable_id: int,
    amount: float,
    source_transaction_id: int | None = None,
    notes: str = "",
    payment_date: str | None = None,
    method: str = "manual",
) -> dict[str, Any]:
    """Register a receivable payment and mirror it as income.

    Important business rule:
    - Additional-card purchases are counted as expenses.
    - When Emily/Sidey pays back, that payment must also enter transactions as
      income so the monthly cashflow is not understated.
    - Only explicit manual payments or transactions with explicit payer evidence
      should reduce receivables. Generic income must never be auto-applied.
    """
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    amount = max(_as_float(amount), 0.0)
    if amount <= 0:
        return {"status": "ERROR", "message": "Monto inválido."}

    with get_connection() as conn:
        _ensure_receivable_tables(conn)
        rec = conn.execute(
            "SELECT * FROM receivables WHERE id = %s AND workspace_id = %s FOR UPDATE",
            (receivable_id, workspace_id),
        ).fetchone()
        if not rec:
            return {"status": "NOT_FOUND", "message": "Cuenta por cobrar no encontrada."}

        pending = _as_float(rec["pending_amount"])
        # Overpayments are valid: a negative balance means the person has credit
        # in their favor and must remain visible instead of being clipped to zero.
        payment = round(amount, 2)
        person_name = str(rec["person_name"] or "Cuenta por cobrar").strip()
        clean_method = (method or "manual").strip() or "manual"
        clean_notes = (notes or "").strip()
        safe_payment_date = None
        if payment_date:
            try:
                safe_payment_date = datetime.fromisoformat(str(payment_date)[:10]).date().isoformat()
            except Exception:
                safe_payment_date = date.today().isoformat()
        else:
            safe_payment_date = date.today().isoformat()

        linked_transaction_id = source_transaction_id
        if linked_transaction_id is None:
            tx_row = conn.execute(
                """
                INSERT INTO transactions (
                    user_id,
                    workspace_id,
                    transaction_date,
                    description,
                    amount,
                    transaction_type,
                    category,
                    account,
                    source,
                    notes,
                    original_amount,
                    original_currency,
                    exchange_rate,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, 'income', 'Cuentas por cobrar', %s, 'receivable_manual', %s, %s, 'CRC', 1, NOW())
                RETURNING id
                """,
                (
                    user_id,
                    workspace_id,
                    safe_payment_date,
                    f"Pago de {person_name}",
                    payment,
                    clean_method,
                    f"Pago manual aplicado a cuenta por cobrar #{receivable_id}. {clean_notes}".strip(),
                    payment,
                ),
            ).fetchone()
            linked_transaction_id = int(tx_row["id"])

        already = conn.execute(
            """
            SELECT id FROM receivable_payments
            WHERE workspace_id = %s
              AND source_transaction_id = %s
            LIMIT 1
            """,
            (workspace_id, linked_transaction_id),
        ).fetchone()
        if already:
            return {"status": "DUPLICATE", "message": "Ese pago ya fue aplicado.", "source_transaction_id": linked_transaction_id}

        new_paid = round(_as_float(rec["paid_amount"]) + payment, 2)
        new_pending = round(_as_float(rec["original_amount"]) - new_paid, 2)
        status = "credit" if new_pending < -0.01 else "completed" if abs(new_pending) <= 0.01 else "partial"

        conn.execute(
            """
            INSERT INTO receivable_payments (user_id, workspace_id, receivable_id, amount, source_transaction_id, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                workspace_id,
                receivable_id,
                payment,
                linked_transaction_id,
                f"Pago registrado manualmente. Método: {clean_method}. {clean_notes}".strip(),
            ),
        )
        payment_day = datetime.fromisoformat(safe_payment_date).date()
        cycle_start, cycle_end = _card_cycle_bounds(payment_day)
        conn.execute(
            """
            INSERT INTO receivable_entries (
                user_id, workspace_id, receivable_id, entry_type, amount, description,
                entry_date, source_type, source_key, source_transaction_id,
                cycle_start, cycle_end, is_archived
            )
            VALUES (%s, %s, %s, 'payment', %s, %s, %s, 'manual_payment', %s, %s, %s, %s, FALSE)
            ON CONFLICT DO NOTHING
            """,
            (
                user_id,
                workspace_id,
                receivable_id,
                payment,
                f"Pago recibido por {clean_method}. {clean_notes}".strip(),
                safe_payment_date,
                f"payment_transaction:{linked_transaction_id}",
                linked_transaction_id,
                cycle_start,
                cycle_end,
            ),
        )
        updated = _recalculate_receivable(conn, user_id, receivable_id)
        conn.commit()

    return {
        "status": "OK",
        "item": dict(updated),
        "applied_amount": round(payment, 2),
        "source_transaction_id": linked_transaction_id,
    }


def _ensure_account_tables(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_balances (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            account_name TEXT NOT NULL, bank_name TEXT NOT NULL DEFAULT '',
            account_type TEXT NOT NULL DEFAULT 'checking', account_last4 TEXT NOT NULL DEFAULT '',
            currency TEXT NOT NULL DEFAULT 'CRC', current_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
            annual_interest_rate NUMERIC(8,4) NOT NULL DEFAULT 0,
            last_reconciliation_difference NUMERIC(18,2) NOT NULL DEFAULT 0,
            balance_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(), source TEXT NOT NULL DEFAULT 'manual',
            include_in_net_worth BOOLEAN NOT NULL DEFAULT TRUE, is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(workspace_id, account_name, account_last4)
        )
    """)
    conn.execute("ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS account_type TEXT NOT NULL DEFAULT 'checking'")
    conn.execute("ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS annual_interest_rate NUMERIC(8,4) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS last_reconciliation_difference NUMERIC(18,2) NOT NULL DEFAULT 0")
    conn.execute("""
        UPDATE account_balances
        SET annual_interest_rate=5.5, updated_at=NOW()
        WHERE LOWER(account_name)='multimoney colones' AND account_last4='6126'
          AND annual_interest_rate=0
    """)
    conn.execute("ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS balance_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    conn.execute("ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'")
    conn.execute("ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS include_in_net_worth BOOLEAN NOT NULL DEFAULT TRUE")
    conn.execute("ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    conn.execute("ALTER TABLE account_balances ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_balance_history (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            financial_account_id BIGINT NOT NULL REFERENCES account_balances(id) ON DELETE CASCADE,
            balance NUMERIC(18,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC',
            balance_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), source TEXT NOT NULL DEFAULT 'manual',
            note TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    conn.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS financial_account_id BIGINT REFERENCES account_balances(id) ON DELETE SET NULL")
    conn.execute("""
        CREATE OR REPLACE FUNCTION jarvis_link_financial_account() RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.financial_account_id IS NULL AND NULLIF(BTRIM(NEW.account),'') IS NOT NULL THEN
                SELECT id INTO NEW.financial_account_id
                FROM account_balances
                WHERE workspace_id=NEW.workspace_id AND is_active=TRUE
                  AND (LOWER(BTRIM(account_name))=LOWER(BTRIM(NEW.account))
                       OR (account_last4<>'' AND NEW.account LIKE CHR(37) || account_last4))
                ORDER BY CASE WHEN LOWER(BTRIM(account_name))=LOWER(BTRIM(NEW.account)) THEN 0 ELSE 1 END,id
                LIMIT 1;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    conn.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trg_transactions_financial_account') THEN
                CREATE TRIGGER trg_transactions_financial_account
                BEFORE INSERT OR UPDATE OF account, financial_account_id ON transactions
                FOR EACH ROW EXECUTE FUNCTION jarvis_link_financial_account();
            END IF;
        END $$
    """)


def list_account_balances() -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_account_tables(conn)
        rows = conn.execute(
            """
            SELECT a.id, a.account_name, a.bank_name, a.account_type, a.account_last4, a.currency, a.annual_interest_rate,
                   a.last_reconciliation_difference,
                   a.current_balance, a.balance_as_of, a.source, a.include_in_net_worth, a.is_active, a.updated_at,
                   COALESCE(m.movement_delta,0) AS movement_delta,
                   a.current_balance + COALESCE(m.movement_delta,0) AS calculated_balance,
                   COALESCE(m.movement_count,0) AS movements_since_balance
            FROM account_balances a
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS movement_count,
                       COALESCE(SUM(CASE
                           WHEN t.transaction_type IN ('income','refund','reimbursement') THEN t.amount
                           WHEN t.transaction_type IN ('expense','debt_payment') THEN -t.amount
                           ELSE 0 END),0) AS movement_delta
                FROM transactions t
                WHERE t.workspace_id=a.workspace_id AND t.financial_account_id=a.id
                  AND t.created_at > a.balance_as_of
            ) m ON TRUE
            WHERE a.workspace_id = %s AND COALESCE(a.is_active, true) = true
            ORDER BY a.bank_name, a.account_name
            """,
            (workspace_id,),
        ).fetchall()
        rates = conn.execute("SELECT DISTINCT ON(currency) currency, exchange_rate FROM exchange_rates WHERE workspace_id=%s ORDER BY currency, rate_date DESC, id DESC", (workspace_id,)).fetchall()
        ibkr_table = conn.execute("SELECT to_regclass('public.investment_portfolio_snapshots') AS table_name").fetchone()
        ibkr = conn.execute("""
            SELECT id, account_id_masked, currency, market_value, market_value_crc, snapshot_at
            FROM investment_portfolio_snapshots
            WHERE workspace_id=%s AND source='ibkr_readonly' AND account_mode='live'
            ORDER BY snapshot_at DESC NULLS LAST,id DESC LIMIT 1
        """, (workspace_id,)).fetchone() if ibkr_table and ibkr_table.get("table_name") else None
    rate_map = {str(row["currency"]).upper(): _as_float(row["exchange_rate"], 1) for row in rates}
    items = [dict(row) for row in rows]
    for item in items:
        currency = str(item.get("currency") or "CRC").upper()
        item["balance_crc"] = round(_as_float(item.get("calculated_balance")) * (1 if currency == "CRC" else rate_map.get(currency, 1)), 2)
        balance = max(_as_float(item.get("calculated_balance")), 0)
        annual_rate = max(_as_float(item.get("annual_interest_rate")), 0)
        item["projected_interest_monthly"] = round(balance * annual_rate / 100 / 12, 2)
        item["projected_interest_annual"] = round(balance * annual_rate / 100, 2)
    included = [item for item in items if item.get("include_in_net_worth")]
    liquid_total = round(sum(_as_float(i.get("balance_crc")) for i in included), 2)
    if ibkr:
        items.append({
            "id": f"ibkr-{ibkr['id']}", "account_name": f"IBKR {ibkr.get('account_id_masked') or ''}".strip(),
            "bank_name": "Interactive Brokers", "account_type": "investment", "account_last4": "",
            "currency": ibkr.get("currency") or "USD", "current_balance": _as_float(ibkr.get("market_value")),
            "balance_crc": _as_float(ibkr.get("market_value_crc")), "balance_as_of": ibkr.get("snapshot_at"),
            "source": "ibkr_flex", "include_in_net_worth": True, "is_active": True, "read_only": True,
        })
    return {"status": "OK", "items": items, "total_real_balance": liquid_total, "currency": "CRC"}


def upsert_account_balance(account_name: str, current_balance: float, bank_name: str = "", account_last4: str = "", currency: str = "CRC", account_type: str = "checking", annual_interest_rate: float = 0, include_in_net_worth: bool = True, source: str = "manual", note: str = "") -> dict[str, Any]:
    user_id = get_current_user_id()  # legacy compatibility during migration
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_account_tables(conn)
        existing = conn.execute(
            """
            SELECT a.id, a.current_balance, a.source,
                   a.current_balance + COALESCE((
                       SELECT SUM(CASE
                           WHEN t.transaction_type IN ('income','refund','reimbursement') THEN t.amount
                           WHEN t.transaction_type IN ('expense','debt_payment') THEN -t.amount
                           ELSE 0 END)
                       FROM transactions t
                       WHERE t.workspace_id=a.workspace_id AND t.financial_account_id=a.id
                         AND t.created_at > a.balance_as_of
                   ),0) AS expected_balance
            FROM account_balances a
            WHERE a.workspace_id = %s AND LOWER(a.account_name) = LOWER(%s) AND COALESCE(a.account_last4,'') = COALESCE(%s,'')
            LIMIT 1
            """,
            (workspace_id, account_name, account_last4),
        ).fetchone()
        if existing:
            reconciliation_difference = 0.0 if existing.get("source") == "transaction_backfill" else current_balance - _as_float(existing.get("expected_balance"))
            row = conn.execute(
                """
                UPDATE account_balances
                SET bank_name=%s, account_type=%s, currency=%s, current_balance=%s, annual_interest_rate=%s,
                    last_reconciliation_difference=%s,
                    balance_as_of=NOW(), source=%s, include_in_net_worth=%s, is_active=true, updated_at=NOW()
                WHERE id = %s AND workspace_id = %s
                RETURNING *
                """,
                (bank_name, account_type, currency.upper(), current_balance, max(annual_interest_rate, 0), reconciliation_difference, source, include_in_net_worth, existing["id"], workspace_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO account_balances (user_id, workspace_id, account_name, bank_name, account_type, account_last4, currency, current_balance, annual_interest_rate, source, include_in_net_worth)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (user_id, workspace_id, account_name, bank_name, account_type, account_last4, currency.upper(), current_balance, max(annual_interest_rate, 0), source, include_in_net_worth),
            ).fetchone()
        conn.execute("""INSERT INTO account_balance_history(user_id,workspace_id,financial_account_id,balance,currency,source,note)
                        VALUES(%s,%s,%s,%s,%s,%s,%s)""", (user_id, workspace_id, row["id"], current_balance, currency.upper(), source, note))
        conn.execute("""UPDATE transactions SET financial_account_id=%s
                        WHERE workspace_id=%s AND financial_account_id IS NULL
                          AND (LOWER(BTRIM(account))=LOWER(BTRIM(%s)) OR (%s<>'' AND account LIKE %s))""",
                     (row["id"], workspace_id, account_name, account_last4, f"%{account_last4}"))
        conn.commit()
    return {"status": "OK", "item": dict(row)}


def deactivate_account_balance(account_id: int) -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_account_tables(conn)
        row = conn.execute("UPDATE account_balances SET is_active=false,updated_at=NOW() WHERE id=%s AND workspace_id=%s RETURNING id", (account_id, workspace_id)).fetchone()
        conn.commit()
    if not row:
        raise ValueError("Cuenta financiera no encontrada.")
    return {"status": "OK", "id": account_id}


def get_real_balance_reconciliation() -> dict[str, Any]:
    accounts = list_account_balances()
    receivables = list_receivables()
    total_real = _as_float(accounts.get("total_real_balance"))
    accountable = [item for item in accounts.get("items", []) if not item.get("read_only")]
    difference = sum(_as_float(item.get("last_reconciliation_difference")) for item in accountable)
    theoretical = total_real - difference
    pending_receivables = _as_float(receivables.get("summary", {}).get("total_pending"))
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
