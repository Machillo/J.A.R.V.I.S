"""Payroll receipts: what a salary deposit was made of. Never an income by themselves.

The bank deposit is the income (one ``transactions`` row, type ``income``, amount = net
deposited). A payroll receipt explains it: gross by concept, deductions, net. This module
stores receipts and their lines, links each one to the deposit it explains, and reads the
composition. It never creates, changes or deletes a transaction, an expense or a debt
payment; a loan repaid through payroll is only linked to its debt for reconciliation.

Matching is conservative and never amount-only. A receipt is MATCHED to an income only when
the amounts are equal to the cent, the deposit falls in the receipt's payment window, and
either the deposit names the receipt's period or it is the only payroll-worded candidate.
Anything weaker stays POSSIBLE_MATCH (for a person to confirm) or PAYROLL_ONLY.

Trust: parsing and authorization are separate. Any well-formed receipt can be parsed, but a
mail receipt is stored only when its sender is trusted by THAT workspace
(``payroll_trusted_senders``, exact address, strict From parse). An untrusted or spoofed
receipt is never stored, so it can never be linked to a deposit.

Shared code: the workspace is always passed explicitly; no employer, person or account is
known here.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any

from backend.email_monitor.sender_trust import single_sender_address, trusted_payroll_sender

INCOME_KINDS = {"ordinary", "overtime", "holiday_paid", "holiday_worked", "vacation", "bonus", "other_income"}
DEDUCTION_KINDS = {"social_security", "income_tax", "association", "loan_repayment", "other_deduction"}
# Parser kinds without a column of their own keep their printed label under the generic kind.
_PARSER_KIND = {"aguinaldo": "other_income", "sick_leave": "other_income", "other": None, "garnishment": "other_deduction"}
# Income categories that are salary (the overview's projection is replaced by them as they arrive).
SALARY_CATEGORIES = {"salario", "horas extra", "bono"}
_PAYROLL_WORDS = re.compile(r"\b(salario|salarial|planilla|nomina|payroll|salary)\b")
_STOPWORDS = {"prestamo", "prestamos", "credito", "creditos", "pago", "pagos", "cuota", "crc", "usd", "del", "los", "las", "por"}
PAYMENT_WINDOW_BEFORE, PAYMENT_WINDOW_AFTER = 3, 10   # days around the issue date (or period end)


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _kind(section: str, parser_kind: str) -> str:
    kind = _PARSER_KIND.get(parser_kind, parser_kind)
    if kind is None or kind not in (INCOME_KINDS if section == "income" else DEDUCTION_KINDS):
        return "other_income" if section == "income" else "other_deduction"
    return kind


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", _plain(text)) if w not in _STOPWORDS}


def _debt_for(conn, workspace_id: str, label: str) -> int | None:
    """The one debt of the workspace whose name the deduction label spells out, else None."""
    words = _tokens(label)
    hits = [int(row["id"]) for row in conn.execute("SELECT id, name FROM debts WHERE workspace_id = %s", (workspace_id,)).fetchall()
            if _tokens(row["name"]) and _tokens(row["name"]) <= words]
    return hits[0] if len(hits) == 1 else None


def record_receipt(conn, *, workspace_id: str, parsed: dict[str, Any], source: str, source_key: str | None = None,
                   sender: str | None = None) -> dict[str, Any]:
    """Store a parsed receipt (``payroll_statement.parse_payroll_receipt``) and try to match it.

    A mail receipt (``source='mail_receipt'``) is stored only when ``sender`` is trusted by this
    workspace; no other source is accepted yet. Idempotent: the same source message or the same
    (period, gross, net) is stored once. A receipt whose lines do not add up is rejected.
    """
    if not parsed or parsed.get("kind") != "payroll_receipt":
        return {"status": "NOT_A_RECEIPT"}
    if source != "mail_receipt":
        return {"status": "UNSUPPORTED_SOURCE"}
    source_address = trusted_payroll_sender(conn, workspace_id, sender or "")
    if not source_address:
        return {"status": "UNTRUSTED_SOURCE"}
    if not parsed.get("consistent"):
        return {"status": "REJECTED_INCONSISTENT"}
    existing = conn.execute(
        """SELECT id FROM payroll_receipts
           WHERE workspace_id = %s AND ((source = %s AND source_key = %s)
              OR (period_start = %s AND period_end = %s AND gross = %s AND net = %s))
           LIMIT 1""",
        (workspace_id, source, source_key, parsed["period_start"], parsed["period_end"], parsed["gross"], parsed["net"]),
    ).fetchone()
    if existing:
        return {"status": "DUPLICATE", "receipt_id": int(existing["id"])}
    receipt_id = int(conn.execute(
        """INSERT INTO payroll_receipts (workspace_id, period_code, period_start, period_end, issue_date, gross, deductions, net,
                                         match_status, source, source_key, source_address)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PAYROLL_ONLY', %s, %s, %s) RETURNING id""",
        (workspace_id, parsed.get("period_code"), parsed["period_start"], parsed["period_end"], parsed.get("issue_date"),
         parsed["gross"], parsed["deductions_total"], parsed["net"], source, source_key, source_address),
    ).fetchone()["id"])
    for section, lines in (("income", parsed["income_lines"]), ("deduction", parsed["deduction_lines"])):
        for line in lines:
            kind = _kind(section, line["kind"])
            debt_id = _debt_for(conn, workspace_id, line["label"]) if kind == "loan_repayment" else None
            conn.execute(
                """INSERT INTO payroll_receipt_lines (workspace_id, receipt_id, section, kind, label, amount, hours, debt_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (workspace_id, receipt_id, section, kind, line["label"][:200], line["amount"], line.get("hours"), debt_id),
            )
    return {"status": "RECORDED", "receipt_id": receipt_id, **match_receipt(conn, workspace_id=workspace_id, receipt_id=receipt_id)}


def _window(receipt: dict[str, Any]) -> tuple[date, date]:
    anchor = receipt.get("issue_date") or receipt["period_end"]
    anchor = anchor if isinstance(anchor, date) else date.fromisoformat(str(anchor)[:10])
    start = receipt["period_start"] if isinstance(receipt["period_start"], date) else date.fromisoformat(str(receipt["period_start"])[:10])
    return max(anchor - timedelta(days=PAYMENT_WINDOW_BEFORE), start), anchor + timedelta(days=PAYMENT_WINDOW_AFTER)


def _names_period(text: str, receipt: dict[str, Any]) -> bool:
    found = set()
    for value in (receipt["period_start"], receipt["period_end"]):
        day = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
        found.add(day.strftime("%d/%m/%Y") in text or day.isoformat() in text)
    return found == {True}


def match_receipt(conn, *, workspace_id: str, receipt_id: int) -> dict[str, Any]:
    """Link a receipt to the one income it explains, or leave it for review. Never creates a transaction."""
    receipt = conn.execute("SELECT * FROM payroll_receipts WHERE id = %s AND workspace_id = %s", (receipt_id, workspace_id)).fetchone()
    if not receipt:
        return {"match_status": "NOT_FOUND"}
    receipt = dict(receipt)
    if receipt["match_status"] == "MATCHED":
        return {"match_status": "MATCHED", "transaction_id": receipt["transaction_id"]}
    first, last = _window(receipt)
    candidates = [dict(row) for row in conn.execute(
        """SELECT t.id, t.transaction_date, t.amount, t.description, t.notes, t.category
           FROM transactions t
           WHERE t.workspace_id = %s AND t.transaction_type = 'income' AND abs(t.amount - %s) < 0.005
             AND t.transaction_date BETWEEN %s AND %s
             AND NOT EXISTS (SELECT 1 FROM payroll_receipts r WHERE r.transaction_id = t.id)
           ORDER BY t.transaction_date, t.id""",
        (workspace_id, receipt["net"], first, last),
    ).fetchall()]
    by_period = [c for c in candidates if _names_period(f"{c.get('description') or ''} {c.get('notes') or ''}", receipt)]
    worded = [c for c in candidates if _PAYROLL_WORDS.search(_plain(f"{c.get('description') or ''} {c.get('category') or ''}"))]
    chosen, reason = None, None
    if len(by_period) == 1:
        chosen, reason = by_period[0], "same net, payment window and period named by the deposit"
    elif not by_period and len(candidates) == 1 and len(worded) == 1:
        chosen, reason = candidates[0], "same net, payment window and the only payroll deposit"
    if chosen:
        conn.execute("UPDATE payroll_receipts SET transaction_id = %s, match_status = 'MATCHED', match_note = %s WHERE id = %s AND workspace_id = %s",
                     (chosen["id"], reason, receipt_id, workspace_id))
        return {"match_status": "MATCHED", "transaction_id": int(chosen["id"])}
    status = "POSSIBLE_MATCH" if candidates else "PAYROLL_ONLY"
    note = ("candidates: " + ", ".join(str(c["id"]) for c in candidates)) if candidates else None
    conn.execute("UPDATE payroll_receipts SET match_status = %s, match_note = %s WHERE id = %s AND workspace_id = %s",
                 (status, note, receipt_id, workspace_id))
    return {"match_status": status, "candidates": [int(c["id"]) for c in candidates]}


def match_pending_for_transaction(conn, *, workspace_id: str, transaction_id: int) -> list[dict[str, Any]]:
    """After an income is recorded, try the receipts still waiting for their deposit."""
    tx = conn.execute("SELECT amount, transaction_type FROM transactions WHERE id = %s AND workspace_id = %s",
                      (transaction_id, workspace_id)).fetchone()
    if not tx or tx["transaction_type"] != "income":
        return []
    waiting = conn.execute(
        """SELECT id FROM payroll_receipts WHERE workspace_id = %s AND match_status IN ('PAYROLL_ONLY', 'POSSIBLE_MATCH', 'UNRESOLVED')
             AND abs(net - %s) < 0.005 ORDER BY issue_date NULLS LAST, id""",
        (workspace_id, tx["amount"]),
    ).fetchall()
    return [match_receipt(conn, workspace_id=workspace_id, receipt_id=int(row["id"])) for row in waiting]


def link_receipt(conn, *, workspace_id: str, receipt_id: int, transaction_id: int) -> dict[str, Any]:
    """A person confirms which income a receipt explains (e.g. a POSSIBLE_MATCH)."""
    receipt = conn.execute("SELECT net FROM payroll_receipts WHERE id = %s AND workspace_id = %s", (receipt_id, workspace_id)).fetchone()
    tx = conn.execute("SELECT amount, transaction_type FROM transactions WHERE id = %s AND workspace_id = %s",
                      (transaction_id, workspace_id)).fetchone()
    if not receipt or not tx:
        return {"status": "NOT_FOUND"}
    if tx["transaction_type"] != "income" or abs(float(tx["amount"]) - float(receipt["net"])) > 0.005:
        return {"status": "ERROR", "message": "El depósito debe ser un ingreso por el neto exacto del comprobante."}
    if conn.execute("SELECT 1 FROM payroll_receipts WHERE transaction_id = %s AND id <> %s", (transaction_id, receipt_id)).fetchone():
        return {"status": "ERROR", "message": "Ese depósito ya explica otro comprobante."}
    conn.execute("UPDATE payroll_receipts SET transaction_id = %s, match_status = 'MATCHED', match_note = 'confirmed by the user' WHERE id = %s AND workspace_id = %s",
                 (transaction_id, receipt_id, workspace_id))
    return {"status": "OK", "match_status": "MATCHED", "transaction_id": transaction_id}


def _detail(receipt: dict[str, Any], lines: list[dict[str, Any]], tx: dict[str, Any] | None) -> dict[str, Any]:
    def by_kind(section: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for line in lines:
            if line["section"] != section:
                continue
            item = out.setdefault(line["kind"], {"amount": 0.0, "hours": None, "lines": []})
            item["amount"] = round(item["amount"] + float(line["amount"]), 2)
            if line.get("hours") is not None:
                item["hours"] = round((item["hours"] or 0) + float(line["hours"]), 2)
            item["lines"].append({"label": line["label"], "amount": float(line["amount"]), "hours": float(line["hours"]) if line.get("hours") is not None else None,
                                  "debt_id": line.get("debt_id")})
        return out

    net = float(receipt["net"])
    return {
        "id": receipt["id"], "period_code": receipt.get("period_code"),
        "period_start": str(receipt["period_start"]), "period_end": str(receipt["period_end"]),
        "issue_date": str(receipt["issue_date"]) if receipt.get("issue_date") else None, "currency": receipt.get("currency"),
        "income": by_kind("income"), "gross": float(receipt["gross"]),
        "deductions": by_kind("deduction"), "deductions_total": float(receipt["deductions"]), "net": net,
        "match_status": receipt["match_status"], "match_note": receipt.get("match_note"),
        "deposit": ({"transaction_id": tx["id"], "date": str(tx["transaction_date"]), "amount": float(tx["amount"]),
                     "account": tx.get("account"), "description": tx.get("description"),
                     "net_equals_deposit": abs(float(tx["amount"]) - net) < 0.005} if tx else None),
        # Deductions never moved money in DINCR; a loan line points to its debt only to reconcile it.
        "deductions_create_movements": False,
    }


def list_receipts(conn, *, workspace_id: str, date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]:
    """Read only: every receipt of the workspace (optionally by issue date) with its composition."""
    receipts = [dict(r) for r in conn.execute(
        """SELECT * FROM payroll_receipts WHERE workspace_id = %s
             AND (%s::date IS NULL OR COALESCE(issue_date, period_end) >= %s::date)
             AND (%s::date IS NULL OR COALESCE(issue_date, period_end) <= %s::date)
           ORDER BY COALESCE(issue_date, period_end), id""",
        (workspace_id, date_from, date_from, date_to, date_to),
    ).fetchall()]
    if not receipts:
        return []
    ids = [r["id"] for r in receipts]
    lines: dict[int, list[dict[str, Any]]] = {}
    for line in conn.execute("SELECT * FROM payroll_receipt_lines WHERE workspace_id = %s AND receipt_id = ANY(%s) ORDER BY id",
                             (workspace_id, ids)).fetchall():
        lines.setdefault(line["receipt_id"], []).append(dict(line))
    tx_ids = [r["transaction_id"] for r in receipts if r.get("transaction_id")]
    txs = {t["id"]: dict(t) for t in conn.execute(
        "SELECT id, transaction_date, amount, account, description FROM transactions WHERE workspace_id = %s AND id = ANY(%s)",
        (workspace_id, tx_ids or [0])).fetchall()}
    return [_detail(r, lines.get(r["id"], []), txs.get(r.get("transaction_id"))) for r in receipts]


def get_receipt(conn, *, workspace_id: str, receipt_id: int) -> dict[str, Any] | None:
    receipt = conn.execute("SELECT * FROM payroll_receipts WHERE id = %s AND workspace_id = %s", (receipt_id, workspace_id)).fetchone()
    if not receipt:
        return None
    lines = [dict(l) for l in conn.execute("SELECT * FROM payroll_receipt_lines WHERE workspace_id = %s AND receipt_id = %s ORDER BY id",
                                           (workspace_id, receipt_id)).fetchall()]
    tx = conn.execute("SELECT id, transaction_date, amount, account, description FROM transactions WHERE workspace_id = %s AND id = %s",
                      (workspace_id, receipt["transaction_id"])).fetchone() if receipt["transaction_id"] else None
    return _detail(dict(receipt), lines, dict(tx) if tx else None)


def salary_received(income_rows: list[dict[str, Any]]) -> float:
    """Salary actually received among a period's income rows (by its salary category)."""
    return round(sum(float(r.get("amount") or 0) for r in income_rows if _plain(r.get("category")).strip() in SALARY_CATEGORIES), 2)


def pending_projection(projected: float, received: float) -> float:
    """The projected salary still to come: received salary replaces the projection, never adds to it."""
    return round(max(float(projected or 0) - float(received or 0), 0.0), 2)


def list_trusted_senders(conn, *, workspace_id: str) -> list[dict[str, Any]]:
    """Read only: the payroll senders this workspace trusts (active and revoked)."""
    return [dict(r) for r in conn.execute(
        "SELECT id, sender_address, label, active, created_at FROM payroll_trusted_senders WHERE workspace_id = %s ORDER BY id",
        (workspace_id,)).fetchall()]


def trust_sender(conn, *, workspace_id: str, sender: str, label: str | None = None) -> dict[str, Any]:
    """Trust one exact sender address for this workspace's payroll receipts (a person's decision)."""
    address = single_sender_address(sender)
    if not address:
        return {"status": "ERROR", "message": "Indicá una sola dirección de correo válida."}
    row = conn.execute(
        """INSERT INTO payroll_trusted_senders (workspace_id, sender_address, label) VALUES (%s, %s, %s)
           ON CONFLICT (workspace_id, sender_address) DO UPDATE SET active = TRUE, label = COALESCE(EXCLUDED.label, payroll_trusted_senders.label), updated_at = NOW()
           RETURNING id, sender_address, label, active""",
        (workspace_id, address, (label or "")[:120] or None)).fetchone()
    return {"status": "OK", "item": dict(row)}


def revoke_trusted_sender(conn, *, workspace_id: str, sender_id: int) -> dict[str, Any]:
    """Stop trusting a sender (kept as history; receipts already stored keep their source)."""
    row = conn.execute("UPDATE payroll_trusted_senders SET active = FALSE, updated_at = NOW() WHERE id = %s AND workspace_id = %s RETURNING id",
                       (sender_id, workspace_id)).fetchone()
    return {"status": "OK"} if row else {"status": "NOT_FOUND"}
