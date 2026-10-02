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

Balances change only inside the operation that changes the money owed (a charge, a
collection, an offset, a confirmed or rejected additional-card purchase). Reading
receivables never writes.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

COLLECTION_TRANSACTION_TYPE = "receivable_payment"
OFFSET_TRANSACTION_TYPE = "receivable_offset"
ASSET_SALE_TRANSACTION_TYPE = "asset_sale"
RECEIVABLE_CATEGORY = "Cuentas por cobrar"
# Existing movements that may be stated to settle a receivable: money that came in, or a
# movement already recorded as a collection. A transfer is excluded (its direction is unknown).
SETTLING_TRANSACTION_TYPES = {"income", "reimbursement", "receivable_payment"}
# A card alias with one of these relationships is the holder's own card even if it was not
# flagged primary; its purchases are never owed by anyone.
HOLDER_RELATIONSHIPS = ("principal", "titular", "holder", "owner")

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


def card_cycle_bounds(today: date | None = None, cutoff_day: int = 21) -> tuple[date, date]:
    """The card cycle [start, end) containing ``today``; it closes on ``cutoff_day``."""
    today = today or date.today()
    cutoff_day = min(max(int(cutoff_day or 21), 1), 28)
    if today.day >= cutoff_day:
        start = today.replace(day=cutoff_day)
    else:
        start = date(today.year - 1, 12, cutoff_day) if today.month == 1 else date(today.year, today.month - 1, cutoff_day)
    end = date(start.year + 1, 1, cutoff_day) if start.month == 12 else date(start.year, start.month + 1, cutoff_day)
    return start, end


def person_key(person_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(person_name or "").strip().lower())
    return normalized.strip("-") or "persona"


def lock_workspace_receivables(conn, workspace_id: str) -> None:
    """Serialize receivable writes of one workspace until the transaction ends.

    Two concurrent operations (a mail scan and a manual payment) must not create the
    same person twice or apply the same movement twice.
    """
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"receivables:{workspace_id}",))


def recalculate(conn, workspace_id: str, receivable_id: int) -> dict[str, Any]:
    """Store the balance of a receivable as derived from its ledger."""
    ledger = [dict(e) for e in conn.execute(
        "SELECT entry_type, amount, is_archived FROM receivable_entries WHERE workspace_id = %s AND receivable_id = %s",
        (workspace_id, receivable_id)).fetchall()]
    totals = receivable_totals(ledger)
    row = conn.execute(
        """UPDATE receivables SET original_amount = %s, paid_amount = %s, pending_amount = %s, status = %s, updated_at = NOW()
           WHERE id = %s AND workspace_id = %s RETURNING *""",
        (totals["original_amount"], totals["paid_amount"], totals["pending_amount"], totals["status"], receivable_id, workspace_id),
    ).fetchone()
    return dict(row) if row else {}


def find_person_receivable(conn, workspace_id: str, person_name: str) -> dict[str, Any] | None:
    """The one receivable row every operation uses for a person (charges and collections alike)."""
    row = conn.execute(
        """
        SELECT * FROM receivables
        WHERE workspace_id = %s AND LOWER(TRIM(person_name)) = LOWER(TRIM(%s))
        ORDER BY CASE source_type WHEN 'additional_card_auto' THEN 1 ELSE 2 END, id ASC
        LIMIT 1
        """,
        (workspace_id, str(person_name or "").strip()),
    ).fetchone()
    return dict(row) if row else None


def person_receivable(conn, workspace_id: str, person_name: str) -> dict[str, Any]:
    """The workspace's receivable account for ``person_name``, created when missing."""
    clean_name = str(person_name or "").strip()
    if not clean_name:
        raise ValueError("La persona es obligatoria.")
    lock_workspace_receivables(conn, workspace_id)
    row = find_person_receivable(conn, workspace_id, clean_name)
    if row:
        return row
    return dict(conn.execute(
        """INSERT INTO receivables (workspace_id, person_name, original_amount, paid_amount, pending_amount, status, notes, source_type, source_key)
           VALUES (%s, %s, 0, 0, 0, 'completed', '', 'person_account', %s) RETURNING *""",
        (workspace_id, clean_name, f"person:{person_key(clean_name)}"),
    ).fetchone())


def additional_card_totals(conn, workspace_id: str, cycle_start: date, cycle_end: date) -> list[dict[str, Any]]:
    """Per person, the confirmed purchases of the workspace's additional cards in one cycle.

    A card is additional only when the workspace marked its alias as not primary and its
    relationship is not the holder's.
    """
    rows = conn.execute(
        """
        WITH additional_aliases AS (
            SELECT workspace_id, card_last4, owner_label FROM card_aliases
            WHERE workspace_id = %s AND COALESCE(is_primary, FALSE) = FALSE
              AND LOWER(TRIM(COALESCE(relationship, ''))) <> ALL(%s)
        ), candidate_movements AS (
            SELECT COALESCE(a.owner_label, c.card_owner) AS person_name, COALESCE(a.card_last4, c.card_last4) AS card_last4,
                   COALESCE(c.transaction_id, c.id * -1) AS movement_key, c.amount
            FROM email_transaction_candidates c
            LEFT JOIN additional_aliases a ON a.workspace_id = c.workspace_id AND a.card_last4 = c.card_last4
            WHERE c.workspace_id = %s AND c.transaction_type = 'expense' AND COALESCE(c.amount, 0) > 0
              AND c.transaction_date >= %s AND c.transaction_date < %s
              AND COALESCE(c.status, '') IN ('confirmed', 'auto_saved', 'imported')
              AND (a.card_last4 IS NOT NULL
                   OR LOWER(TRIM(COALESCE(c.card_owner, ''))) IN (SELECT LOWER(TRIM(owner_label)) FROM additional_aliases))
        )
        SELECT person_name, COALESCE(SUM(amount), 0) AS total_amount, COUNT(DISTINCT movement_key) AS movement_count,
               ARRAY_AGG(DISTINCT card_last4 ORDER BY card_last4) FILTER (WHERE card_last4 IS NOT NULL AND card_last4 <> '') AS cards
        FROM candidate_movements WHERE COALESCE(person_name, '') <> '' GROUP BY person_name ORDER BY person_name
        """,
        (workspace_id, list(HOLDER_RELATIONSHIPS), workspace_id, cycle_start, cycle_end),
    ).fetchall()
    return [dict(row) for row in rows]


def mirror_additional_card_cycle(conn, workspace_id: str, day: date | None = None) -> int:
    """Make the cycle's additional-card charges equal the cycle's confirmed purchases.

    Called by the operations that confirm, save or reject a card purchase (and by the
    explicit repair sync), never by a read. One charge per person and cycle; a person
    whose purchases were all rejected has that cycle's charge archived, not deleted.
    Idempotent. Returns how many receivables were recalculated.
    """
    lock_workspace_receivables(conn, workspace_id)
    cycle_start, cycle_end = card_cycle_bounds(day)
    wanted: dict[str, tuple[int, float, str]] = {}
    for row in additional_card_totals(conn, workspace_id, cycle_start, cycle_end):
        person = str(row.get("person_name") or "").strip()
        amount = round(max(float(row.get("total_amount") or 0), 0.0), 2)
        if not person or amount <= 0:
            continue
        account = person_receivable(conn, workspace_id, person)
        cards = ", ".join(row.get("cards") or []) or "sin tarjeta"
        description = f"Compras de tarjetas adicionales del ciclo {cycle_start.isoformat()} a {cycle_end.isoformat()} ({cards})"
        wanted[f"additional_cards:{person_key(person)}:{cycle_start.isoformat()}"] = (int(account["id"]), amount, description)
    touched: set[int] = set()
    for source_key, (receivable_id, amount, description) in wanted.items():
        conn.execute(
            """
            INSERT INTO receivable_entries (workspace_id, receivable_id, entry_type, amount, description, entry_date,
                                            source_type, source_key, cycle_start, cycle_end, is_archived)
            VALUES (%s, %s, 'charge', %s, %s, %s, 'additional_card_auto', %s, %s, %s, FALSE)
            ON CONFLICT (workspace_id, source_key) WHERE source_key IS NOT NULL
            DO UPDATE SET receivable_id = EXCLUDED.receivable_id, amount = EXCLUDED.amount, description = EXCLUDED.description,
                          entry_date = EXCLUDED.entry_date, cycle_start = EXCLUDED.cycle_start, cycle_end = EXCLUDED.cycle_end,
                          is_archived = FALSE
            """,
            (workspace_id, receivable_id, amount, description, cycle_start, source_key, cycle_start, cycle_end),
        )
        touched.add(receivable_id)
    stale = conn.execute(
        """SELECT id, receivable_id, source_key FROM receivable_entries
           WHERE workspace_id = %s AND source_type = 'additional_card_auto' AND cycle_start = %s AND NOT COALESCE(is_archived, FALSE)""",
        (workspace_id, cycle_start),
    ).fetchall()
    for entry in stale:
        if entry["source_key"] not in wanted:
            conn.execute("UPDATE receivable_entries SET is_archived = TRUE WHERE id = %s AND workspace_id = %s", (entry["id"], workspace_id))
            touched.add(int(entry["receivable_id"]))
    for receivable_id in touched:
        recalculate(conn, workspace_id, receivable_id)
    return len(touched)


_COLLECTION_ORIGINS = {"correo": "email_collection", "sync": "income_auto"}


def link_collection(conn, *, workspace_id: str, person: str, transaction_id: int,
                    amount: float, entry_date: str, description: str, origin: str = "correo") -> bool:
    """Record an existing cash movement, detected automatically, as ``person``'s collection.

    Only when the person still owes at least that amount: an automatic match never turns
    money that was not owed into a "collection" (a gift, a shared bill, an overpayment stay
    income for the user to decide). The movement becomes a ``receivable_payment`` (money in,
    not income) with its previous type kept in the notes; the ledger gets one payment entry
    and the balance is recalculated from the ledger. Idempotent per movement. Returns False
    when nothing was applied.
    """
    lock_workspace_receivables(conn, workspace_id)
    rec = find_person_receivable(conn, workspace_id, person)
    amount = round(float(amount or 0), 2)
    entry_date = entry_date or date.today().isoformat()
    if not rec or amount <= 0 or is_movement_applied(conn, workspace_id, transaction_id):
        return False
    ledger = [dict(e) for e in conn.execute(
        "SELECT entry_type, amount, is_archived FROM receivable_entries WHERE workspace_id = %s AND receivable_id = %s",
        (workspace_id, rec["id"])).fetchall()]
    if amount > receivable_totals(ledger)["pending_amount"] + 0.01:
        return False
    conn.execute(
        """
        UPDATE transactions
        SET transaction_type = %s, category = %s,
            notes = CONCAT_WS(' | ', NULLIF(notes, ''), 'Cobro de cuenta por cobrar (tipo anterior: ' || transaction_type || ')')
        WHERE id = %s AND workspace_id = %s AND transaction_type IN ('income', 'reimbursement')
        """,
        (COLLECTION_TRANSACTION_TYPE, RECEIVABLE_CATEGORY, transaction_id, workspace_id),
    )
    conn.execute(
        """
        INSERT INTO receivable_payments (workspace_id, receivable_id, amount, source_transaction_id, notes)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (workspace_id, rec["id"], amount, transaction_id, f"Cobro detectado ({origin}): {description}"[:300]),
    )
    conn.execute(
        """
        INSERT INTO receivable_entries (workspace_id, receivable_id, entry_type, amount, description, entry_date,
                                        source_type, source_key, source_transaction_id, is_archived)
        VALUES (%s, %s, 'payment', %s, %s, %s, %s, %s, %s, FALSE)
        ON CONFLICT DO NOTHING
        """,
        (workspace_id, rec["id"], amount, f"Cobro: {description}"[:300], entry_date,
         _COLLECTION_ORIGINS.get(origin, "email_collection"), f"payment_transaction:{transaction_id}", transaction_id),
    )
    recalculate(conn, workspace_id, int(rec["id"]))
    return True


def is_movement_applied(conn, workspace_id: str, transaction_id: int) -> bool:
    """Whether a movement already settles some receivable (in the ledger or its legacy mirror)."""
    return bool(conn.execute(
        """SELECT 1 FROM receivable_entries WHERE workspace_id = %s AND source_transaction_id = %s
           UNION ALL SELECT 1 FROM receivable_payments WHERE workspace_id = %s AND source_transaction_id = %s LIMIT 1""",
        (workspace_id, transaction_id, workspace_id, transaction_id),
    ).fetchone())
