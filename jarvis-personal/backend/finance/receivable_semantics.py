"""What money owed to the user means, and what settling it does.

A receivable is created by a charge whose kind says why the person owes:

- ``installment_sale``: the user sold something they owned and is paid in instalments.
  The sale is ONE economic event (the charge); later collections only reduce it.
- ``loan`` / ``transfer`` / ``cash``: money the user lent or advanced.
- ``purchase``: something the user paid on the person's behalf (a reimbursable expense).
- ``additional_card``: purchases made with an additional card billed to the user.

Settling a receivable never creates earned income:

- a cash collection (SINPE, transfer, deposit, cash) is a ``receivable_payment``: money
  in, receivable down, not income and not a reversed expense;
- a non-cash offset (both people owed each other and the debts were netted) is a
  ``receivable_offset``: receivable down, no money moved, no income, no expense.

Who paid is matched against the workspace's own data (its receivable people), never
against names written in code.
"""
from __future__ import annotations

import re
from typing import Any

COLLECTION_TRANSACTION_TYPE = "receivable_payment"
OFFSET_TRANSACTION_TYPE = "receivable_offset"
ASSET_SALE_TRANSACTION_TYPE = "asset_sale"
RECEIVABLE_CATEGORY = "Cuentas por cobrar"

CASH_METHODS = {"manual", "sinpe", "transfer", "transferencia", "deposit", "deposito", "depósito", "cash", "efectivo"}
OFFSET_METHODS = {"offset", "non_cash_offset", "compensacion", "compensación"}

CHARGE_KINDS = {
    "purchase": "Compra pagada por cuenta de la persona",
    "loan": "Dinero prestado",
    "transfer": "Transferencia prestada",
    "cash": "Efectivo prestado",
    "installment_sale": "Venta a plazos de un bien propio",
    "other": "Cuenta por cobrar manual",
}

_PAYMENT_CONTEXT = ("sinpe", "transferencia", "abono", "pago", "reembolso", "payer=", "remitente", "origen", "deposito", "depósito")


def charge_kind(value: str | None) -> str:
    kind = str(value or "purchase").strip().lower()
    return kind if kind in CHARGE_KINDS else "other"


def settlement(method: str | None) -> dict[str, Any]:
    """Transaction fields for settling a receivable with ``method``.

    Returns ``{"transaction_type", "account", "entry_source_type", "is_cash", "method"}``.
    Unknown methods are treated as cash collections (money did arrive), never as income.
    """
    clean = str(method or "manual").strip().lower() or "manual"
    if clean in OFFSET_METHODS:
        return {"transaction_type": OFFSET_TRANSACTION_TYPE, "account": "Compensación sin efectivo",
                "entry_source_type": "non_cash_offset", "is_cash": False, "method": "non_cash_offset"}
    return {"transaction_type": COLLECTION_TRANSACTION_TYPE, "account": None,
            "entry_source_type": "manual_payment", "is_cash": True, "method": clean}


def receivable_totals(entries: list[dict[str, Any]]) -> dict[str, float]:
    """Charged, paid and pending of a receivable from its ledger entries (pure)."""
    active = [e for e in entries if not e.get("is_archived")]
    charged = round(max(sum(float(e.get("amount") or 0) for e in active if e.get("entry_type") == "charge"), 0.0), 2)
    paid = round(max(sum(float(e.get("amount") or 0) for e in active if e.get("entry_type") == "payment"), 0.0), 2)
    pending = round(charged - paid, 2)
    status = "credit" if pending < -0.01 else "completed" if abs(pending) <= 0.01 else "partial" if paid > 0 else "pending"
    return {"original_amount": charged, "paid_amount": paid, "pending_amount": pending, "status": status}


def payer_from_text(text: str, people: list[str]) -> str | None:
    """The receivable person a payment names, matched against the workspace's own people.

    Requires payment context and a whole-word match of exactly one person's name, so a
    generic income can never reduce someone's balance by accident.
    """
    clean = (text or "").lower()
    if not any(token in clean for token in _PAYMENT_CONTEXT):
        return None
    matches = []
    for person in people:
        name = str(person or "").strip()
        if len(name) >= 3 and re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", clean):
            matches.append(name)
    return matches[0] if len(set(m.lower() for m in matches)) == 1 else None


def receivable_people(conn, workspace_id: str) -> list[str]:
    rows = conn.execute("SELECT DISTINCT person_name FROM receivables WHERE workspace_id = %s", (workspace_id,)).fetchall()
    return [str(row["person_name"]) for row in rows if row.get("person_name")]


def link_collection(conn, *, workspace_id: str, person: str, transaction_id: int,
                    amount: float, entry_date: str, description: str) -> bool:
    """Record an existing cash movement as the collection of ``person``'s receivable.

    The movement becomes a ``receivable_payment`` (money in, not income), the ledger gets
    one payment entry, and the balance is recalculated from the ledger. Idempotent per
    movement. Returns False when there is nothing to apply.
    """
    rec = conn.execute(
        "SELECT id FROM receivables WHERE workspace_id = %s AND LOWER(TRIM(person_name)) = LOWER(TRIM(%s)) ORDER BY id LIMIT 1",
        (workspace_id, person),
    ).fetchone()
    if not rec or float(amount or 0) <= 0:
        return False
    if conn.execute("SELECT 1 FROM receivable_entries WHERE workspace_id = %s AND source_transaction_id = %s LIMIT 1",
                    (workspace_id, transaction_id)).fetchone():
        return False
    conn.execute("UPDATE transactions SET transaction_type = %s WHERE id = %s AND workspace_id = %s AND transaction_type IN ('income', 'reimbursement')",
                 (COLLECTION_TRANSACTION_TYPE, transaction_id, workspace_id))
    conn.execute("INSERT INTO receivable_payments (workspace_id, receivable_id, amount, source_transaction_id, notes) VALUES (%s, %s, %s, %s, %s)",
                 (workspace_id, rec["id"], round(float(amount), 2), transaction_id, f"Cobro detectado desde correo: {description}"[:300]))
    conn.execute(
        """INSERT INTO receivable_entries (workspace_id, receivable_id, entry_type, amount, description, entry_date, source_type, source_key, source_transaction_id, is_archived)
           VALUES (%s, %s, 'payment', %s, %s, %s, 'email_collection', %s, %s, FALSE) ON CONFLICT DO NOTHING""",
        (workspace_id, rec["id"], round(float(amount), 2), f"Cobro: {description}"[:300], entry_date, f"payment_transaction:{transaction_id}", transaction_id),
    )
    ledger = [dict(e) for e in conn.execute("SELECT entry_type, amount, is_archived FROM receivable_entries WHERE workspace_id = %s AND receivable_id = %s",
                                            (workspace_id, rec["id"])).fetchall()]
    totals = receivable_totals(ledger)
    conn.execute("UPDATE receivables SET original_amount = %s, paid_amount = %s, pending_amount = %s, status = %s, updated_at = NOW() WHERE id = %s AND workspace_id = %s",
                 (totals["original_amount"], totals["paid_amount"], totals["pending_amount"], totals["status"], rec["id"], workspace_id))
    return True
