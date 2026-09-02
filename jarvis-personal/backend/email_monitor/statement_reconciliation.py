from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from backend.finance.category_catalog import normalize_category
from backend.transactions.parser import detect_category


DATE_LINE = re.compile(r"(?m)^(\d{2}/\d{2}/\d{4})\s*$")
MONEY_LINE = re.compile(r"^-?[\d,]+\.\d{2}$")


def _plain(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().lower()


def _amount(value: str) -> float:
    return float(value.replace(",", ""))


def parse_multimoney_statement(text: str) -> list[dict[str, Any]]:
    """Parse MultiMoney's extracted movement table without depending on PDF layout coordinates."""
    matches = list(DATE_LINE.finditer(text or ""))
    movements: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        lines = [line.strip() for line in text[match.end():end].splitlines() if line.strip()]
        if len(lines) < 5 or not lines[0].isdigit():
            continue
        money_positions = [i for i, line in enumerate(lines) if MONEY_LINE.fullmatch(line)]
        if len(money_positions) < 3:
            continue
        first = money_positions[0]
        if first < 2 or money_positions[:3] != [first, first + 1, first + 2]:
            continue
        description = " ".join(lines[1:first]).strip()
        debit, credit, balance = (_amount(lines[first + offset]) for offset in range(3))
        if debit <= 0 and credit <= 0:
            continue
        normalized = _plain(description)
        is_internal = "inversion vista smart" in normalized
        is_interest = "capitalizacion normal de intereses" in normalized
        transaction_type = "internal_transfer" if is_internal else "income" if credit > 0 else "expense"
        category = "Transferencia interna" if is_internal else "Inversión" if is_interest else normalize_category(detect_category(description), transaction_type)
        movements.append({
            "transaction_date": datetime.strptime(match.group(1), "%d/%m/%Y").date().isoformat(),
            "reference": lines[0],
            "description": description,
            "debit": debit,
            "credit": credit,
            "amount": debit if debit > 0 else credit,
            "balance": balance,
            "direction": "out" if debit > 0 else "in",
            "transaction_type": transaction_type,
            "category": category,
            "ignored": is_internal,
        })
    return movements


def ensure_statement_reconciliation_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_statement_reconciliation_lines (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            workspace_id UUID NOT NULL,
            statement_document_id BIGINT NOT NULL REFERENCES email_statement_documents(id) ON DELETE CASCADE,
            transaction_date DATE NOT NULL,
            reference TEXT NOT NULL,
            description TEXT NOT NULL,
            amount NUMERIC(14,2) NOT NULL,
            debit NUMERIC(14,2) NOT NULL DEFAULT 0,
            credit NUMERIC(14,2) NOT NULL DEFAULT 0,
            balance NUMERIC(14,2),
            transaction_type TEXT NOT NULL,
            category TEXT NOT NULL,
            reconciliation_status TEXT NOT NULL,
            matched_transaction_id BIGINT,
            reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (workspace_id, statement_document_id, reference, transaction_date, amount)
        )
        """
    )


def reconcile_statement(conn, *, user_id: int, workspace_id: str, statement_id: int) -> dict[str, Any]:
    ensure_statement_reconciliation_tables(conn)
    document = conn.execute(
        """
        SELECT * FROM email_statement_documents
        WHERE id = %s AND workspace_id = %s
        """,
        (statement_id, workspace_id),
    ).fetchone()
    if not document:
        raise HTTPException(status_code=404, detail="Estado de cuenta no encontrado.")
    document = dict(document)
    if document.get("bank") != "multimoney":
        raise HTTPException(status_code=400, detail="Este primer conciliador admite estados MultiMoney.")
    movements = parse_multimoney_statement(document.get("extracted_text") or "")
    if not movements:
        raise HTTPException(status_code=422, detail="No pude extraer movimientos del PDF de MultiMoney.")

    counts = {"matched": 0, "missing": 0, "ambiguous": 0, "ignored": 0}
    for movement in movements:
        matched_id = None
        if movement["ignored"]:
            status = "ignored"
            reason = "Traslado interno hacia Inversión Vista Smart; no se duplica como ingreso."
        else:
            rows = conn.execute(
                """
                SELECT id, description, transaction_type
                FROM transactions
                WHERE workspace_id = %s
                  AND transaction_date::date = %s::date
                  AND ABS(amount - %s) < 0.01
                ORDER BY id
                """,
                (workspace_id, movement["transaction_date"], movement["amount"]),
            ).fetchall()
            if len(rows) == 1:
                status = "matched"
                matched_id = int(rows[0]["id"])
                reason = "Coincide exactamente por fecha y monto con Finanzas."
            elif len(rows) > 1:
                status = "ambiguous"
                reason = "Hay varias transacciones con la misma fecha y monto; requiere revisión."
            else:
                status = "missing"
                reason = "Aparece en el estado de cuenta pero no existe en Finanzas."
        counts[status] += 1
        conn.execute(
            """
            INSERT INTO email_statement_reconciliation_lines (
                user_id, workspace_id, statement_document_id, transaction_date, reference,
                description, amount, debit, credit, balance, transaction_type, category,
                reconciliation_status, matched_transaction_id, reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, statement_document_id, reference, transaction_date, amount)
            DO UPDATE SET
                description = EXCLUDED.description,
                debit = EXCLUDED.debit,
                credit = EXCLUDED.credit,
                balance = EXCLUDED.balance,
                transaction_type = EXCLUDED.transaction_type,
                category = EXCLUDED.category,
                reconciliation_status = EXCLUDED.reconciliation_status,
                matched_transaction_id = EXCLUDED.matched_transaction_id,
                reason = EXCLUDED.reason,
                updated_at = NOW()
            """,
            (
                user_id, workspace_id, statement_id, movement["transaction_date"], movement["reference"],
                movement["description"], movement["amount"], movement["debit"], movement["credit"],
                movement["balance"], movement["transaction_type"], movement["category"], status,
                matched_id, reason,
            ),
        )
    final_status = "reconciled" if counts["missing"] == 0 and counts["ambiguous"] == 0 else "needs_review"
    conn.execute(
        "UPDATE email_statement_documents SET status = %s, updated_at = NOW() WHERE id = %s AND workspace_id = %s",
        (final_status, statement_id, workspace_id),
    )
    return {"status": "OK", "statement_id": statement_id, "movements": len(movements), "summary": counts, "reconciliation_status": final_status}
