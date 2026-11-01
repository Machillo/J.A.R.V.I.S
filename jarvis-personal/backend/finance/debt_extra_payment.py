"""An extraordinary payment to a debt's principal, inside the caller's transaction.

The one way a pure extra payment is recorded: the debt's remaining balance goes down, a
``debt_payments`` row ('extra_payment') keeps the before/after, and a ``debt_payment``
transaction records the money that left. Nothing is committed here: the caller commits, so a
payment that is part of a larger operation (the Owner's confirmed distribution) is applied
together with the rest of it or not at all.

What the bank did with the extra money is the user's to say, never guessed (``adjust_after_extra``):
fewer installments left (the term) or a lower installment. Without it the debt keeps both.
"""
from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


MAX_INSTALLMENTS = 600


def adjust_after_extra(conn, workspace_id: str, debt_id: int, *, remaining_installments: int | None = None,
                       new_monthly_payment: float | None = None) -> None:
    """What the bank did with an extra payment, as the user said it: the installments left
    (``term_months`` = installments already paid + the ones left) or the new installment."""
    if remaining_installments is not None:
        conn.execute(
            "UPDATE debts SET term_months = COALESCE(installments_paid, 0) + %s, updated_at = NOW() WHERE id = %s AND workspace_id = %s",
            (int(remaining_installments), debt_id, workspace_id),
        )
    if new_monthly_payment is not None:
        conn.execute(
            "UPDATE debts SET monthly_payment = %s, updated_at = NOW() WHERE id = %s AND workspace_id = %s",
            (_as_float(new_monthly_payment), debt_id, workspace_id),
        )


def record_extra_payment(
    conn,
    workspace_id: str,
    debt_id: int,
    amount: float,
    *,
    payment_date: str,
    description: str = "",
    new_monthly_payment: float | None = None,
    remaining_installments: int | None = None,
    source: str = "manual_extra",
    transaction_source: str = "manual_debt_extra",
    transaction_note: str = "",
) -> dict[str, Any] | None:
    """Apply ``amount`` to the principal of the workspace's debt; None when it is not the
    workspace's. The principal applied never exceeds the remaining balance (the debt row is
    locked first, so two payments cannot both read the same balance)."""
    debt = conn.execute(
        """
        SELECT id, name, remaining_amount, monthly_payment, installments_paid
        FROM debts WHERE id = %s AND workspace_id = %s
        FOR UPDATE
        """, (debt_id, workspace_id)
    ).fetchone()
    if not debt:
        return None

    previous_balance = _as_float(debt["remaining_amount"])
    previous_payment = _as_float(debt["monthly_payment"])
    principal = min(max(_as_float(amount), 0), previous_balance)
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
            workspace_id, debt_id, payment_type, amount, principal_amount, interest_amount,
            fee_amount, extra_principal_amount, previous_remaining_amount, new_remaining_amount,
            previous_monthly_payment, new_monthly_payment, description, payment_date,
            installment_number, source, created_at
        ) VALUES (%s, %s, 'extra_payment', %s, %s, 0, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (workspace_id, debt_id, principal, principal, principal, previous_balance, final_balance,
         previous_payment, final_payment, description or "Abono extraordinario a principal",
         payment_date, int(debt.get("installments_paid") or 0), source),
    )
    adjust_after_extra(conn, workspace_id, debt_id, remaining_installments=remaining_installments)
    note = f"debt_id:{debt_id};extra_payment_id:{cursor.lastrowid}"
    conn.execute(
        """INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type,
                                  category, account, source, notes, created_at)
           VALUES (%s, %s, %s, %s, 'debt_payment', %s, NULL, %s, %s, NOW())""",
        (workspace_id, payment_date, f"Abono extra {debt['name']}", principal, debt['name'],
         transaction_source, f"{note};{transaction_note}" if transaction_note else note),
    )
    return {
        "payment_id": cursor.lastrowid, "debt_id": debt_id, "debt_name": debt["name"],
        "payment_amount": round(principal, 2), "principal_amount": round(principal, 2),
        "extra_principal_amount": round(principal, 2), "interest_amount": 0, "fee_amount": 0,
        "previous_remaining_amount": round(previous_balance, 2),
        "new_remaining_amount": round(final_balance, 2),
    }
