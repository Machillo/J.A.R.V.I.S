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
BAC_CARD_ROW = re.compile(
    r"^(?P<reference>\d{10,16})\s+"
    r"(?P<date>\d{1,2}-[A-ZÁÉÍÓÚÑ]{3}-\d{2})\s+"
    r"(?P<description>.+?)\s+(?P<currency>CRC|USD)\s+"
    r"(?P<amount>[\d,]+\.\d{2}-?)$",
    re.IGNORECASE,
)
BAC_INTEREST_TOTAL = re.compile(
    r"^Total por concepto de intereses\s+(?P<crc>[\d,]+\.\d{2}-?)\s+(?P<usd>[\d,]+\.\d{2}-?)$",
    re.IGNORECASE,
)
SPANISH_MONTHS = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}


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
        if is_internal:
            category = "Transferencia interna"
        elif is_interest:
            category = "Inversión"
        elif "nutricionista" in normalized:
            category = "Salud"
        elif "bateria" in normalized:
            category = "Transporte"
        else:
            category = normalize_category(detect_category(description), transaction_type)
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


def parse_bac_statement(text: str) -> list[dict[str, Any]]:
    """Parse BAC account statements that expose debit, credit and balance columns.

    Credit-card summaries without explicit debit/credit columns are deliberately
    rejected: importing an unsigned amount would risk reversing a payment or refund.
    """
    if "tarjeta de credito" in _plain(text):
        return _parse_bac_credit_card_statement(text)

    normalized_text = _plain(text)
    has_ledger_columns = (
        ("debito" in normalized_text or "debitos" in normalized_text)
        and ("credito" in normalized_text or "creditos" in normalized_text)
        and "saldo" in normalized_text
    )
    if not has_ledger_columns:
        return []

    matches = list(DATE_LINE.finditer(text or ""))
    movements: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        lines = [line.strip() for line in text[match.end():end].splitlines() if line.strip()]
        money_positions = [i for i, line in enumerate(lines) if MONEY_LINE.fullmatch(line)]
        if len(money_positions) < 3:
            continue
        first = money_positions[0]
        if first < 1 or money_positions[:3] != [first, first + 1, first + 2]:
            continue

        prefix = lines[:first]
        reference = prefix[0] if prefix[0].replace("-", "").isdigit() else f"bac-{match.group(1)}-{index + 1}"
        description_start = 1 if reference == prefix[0] else 0
        description = " ".join(prefix[description_start:]).strip()
        if not description:
            continue
        debit, credit, balance = (_amount(lines[first + offset]) for offset in range(3))
        if (debit > 0) == (credit > 0):
            continue

        normalized = _plain(description)
        is_internal = any(term in normalized for term in (
            "transferencia entre cuentas propias",
            "traslado entre cuentas",
            "inversion vista smart",
        ))
        transaction_type = "internal_transfer" if is_internal else "income" if credit > 0 else "expense"
        category = "Transferencia interna" if is_internal else normalize_category(
            detect_category(description), transaction_type
        )
        movements.append({
            "transaction_date": datetime.strptime(match.group(1), "%d/%m/%Y").date().isoformat(),
            "reference": reference,
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


def _parse_bac_credit_card_date(value: str) -> str:
    day, month_name, year = value.upper().split("-")
    month = SPANISH_MONTHS[month_name]
    return datetime(2000 + int(year), month, int(day)).date().isoformat()


def _parse_bac_credit_card_statement(text: str, exchange_rate: float = 495.0) -> list[dict[str, Any]]:
    """Extract signed detail rows, excluding payments and summary/financing tables."""
    section: str | None = None
    card_last4: str | None = None
    cutoff_date: str | None = None
    movements: list[dict[str, Any]] = []
    allowed_sections = {"purchases", "charges", "voluntary"}

    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        plain = _plain(line)
        cutoff_match = re.match(r"^Fecha de corte:\s*(\d{1,2}-[A-ZÁÉÍÓÚÑ]{3}-\d{2})$", line, re.IGNORECASE)
        if cutoff_match:
            cutoff_date = _parse_bac_credit_card_date(cutoff_match.group(1))
            continue
        if plain.startswith("b) detalle de compras del periodo"):
            section = "purchases"
            continue
        if plain.startswith("c) detalle de intereses"):
            section = "interest"
            continue
        if plain.startswith("d) detalle de otros cargos"):
            section = "charges"
            continue
        if plain.startswith("e) detalle de productos y servicios de eleccion voluntaria"):
            section = "voluntary"
            continue
        if plain.startswith(("f) cargos", "g) otras notas", "total de compras")):
            section = None
            continue

        card_match = re.search(r"\*{8,}(\d{4})", line)
        if card_match:
            card_last4 = card_match.group(1)
            continue
        interest_match = BAC_INTEREST_TOTAL.fullmatch(line) if section == "interest" else None
        if interest_match and cutoff_date:
            for currency, raw_amount in (("CRC", interest_match.group("crc")), ("USD", interest_match.group("usd"))):
                original_amount = _amount(raw_amount.rstrip("-"))
                if original_amount <= 0:
                    continue
                is_credit = raw_amount.endswith("-")
                amount_crc = round(original_amount * exchange_rate, 2) if currency == "USD" else original_amount
                movements.append({
                    "transaction_date": cutoff_date,
                    "reference": f"interest-{card_last4 or 'account'}-{cutoff_date}-{currency}",
                    "description": f"INTERESES TARJETA BAC {card_last4 or ''}".strip(),
                    "debit": 0.0 if is_credit else amount_crc,
                    "credit": amount_crc if is_credit else 0.0,
                    "amount": amount_crc,
                    "balance": None,
                    "direction": "in" if is_credit else "out",
                    "transaction_type": "income" if is_credit else "expense",
                    "category": "Tarjeta BAC",
                    "ignored": False,
                    "original_amount": original_amount,
                    "original_currency": currency,
                    "exchange_rate": exchange_rate if currency == "USD" else None,
                    "card_last4": card_last4,
                    "statement_section": "interest",
                })
            section = None
            continue
        if section not in allowed_sections:
            continue
        match = BAC_CARD_ROW.fullmatch(line)
        if not match:
            continue

        original_amount = _amount(match.group("amount").rstrip("-"))
        # Credits/reversals within these sections carry a trailing minus sign.
        is_credit = match.group("amount").endswith("-")
        currency = match.group("currency").upper()
        amount_crc = round(original_amount * exchange_rate, 2) if currency == "USD" else original_amount
        description = re.sub(r"[_]+", " ", match.group("description")).strip()
        transaction_type = "income" if is_credit else "expense"
        category = normalize_category(detect_category(description), transaction_type)
        movements.append({
            "transaction_date": _parse_bac_credit_card_date(match.group("date")),
            "reference": match.group("reference"),
            "description": description,
            "debit": 0.0 if is_credit else amount_crc,
            "credit": amount_crc if is_credit else 0.0,
            "amount": amount_crc,
            "balance": None,
            "direction": "in" if is_credit else "out",
            "transaction_type": transaction_type,
            "category": category,
            "ignored": False,
            "original_amount": original_amount,
            "original_currency": currency,
            "exchange_rate": exchange_rate if currency == "USD" else None,
            "card_last4": card_last4,
            "statement_section": section,
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
    bank = document.get("bank")
    if bank not in {"multimoney", "bac"}:
        raise HTTPException(status_code=400, detail="La conciliación admite estados MultiMoney y BAC.")
    parser = parse_multimoney_statement if bank == "multimoney" else parse_bac_statement
    movements = parser(document.get("extracted_text") or "")
    if not movements:
        raise HTTPException(status_code=422, detail=f"No pude extraer movimientos seguros del PDF de {bank.upper()}.")

    counts = {"matched": 0, "missing": 0, "ambiguous": 0, "ignored": 0}
    for movement in movements:
        matched_id = None
        if movement["ignored"]:
            status = "ignored"
            reason = "Traslado interno hacia Inversión Vista Smart; no se duplica como ingreso."
        else:
            # A MultiMoney debit and a BAC incoming SINPE can be the two sides
            # of one transfer between the user's own accounts. MultiMoney's
            # statement reference is internal and can differ from BAC's SINPE
            # reference, so match the mirror by date, amount, direction and
            # concept instead of relying only on the reference.
            bac_mirror = conn.execute(
                """
                SELECT c.id
                FROM email_ingested_messages m
                JOIN email_transaction_candidates c ON c.email_message_id = m.id
                WHERE m.workspace_id = %s
                  AND m.bank = 'bac'
                  AND %s = 'out'
                  AND c.transaction_type = 'income'
                  AND c.transaction_date::date = %s::date
                  AND ABS(c.amount - %s) < 0.01
                  AND LOWER(TRIM(c.description)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                (
                    workspace_id,
                    movement["direction"],
                    movement["transaction_date"],
                    movement["amount"],
                    movement["description"],
                ),
            ).fetchone() if bank == "multimoney" else None
            if bac_mirror:
                status = "ignored"
                reason = "Movimiento espejo MultiMoney→BAC por fecha, monto, dirección y concepto; es traslado entre cuentas propias."
                counts[status] += 1
                _upsert_reconciliation_line(conn, user_id, workspace_id, statement_id, movement, status, matched_id, reason)
                continue

            scheduled_proof = None
            if "casa y prestamo" in _plain(movement["description"]):
                scheduled_proof = conn.execute(
                    """
                    SELECT id
                    FROM email_transaction_candidates
                    WHERE workspace_id = %s
                      AND status = 'duplicate'
                      AND transaction_date::date = %s::date
                      AND ABS(amount - %s) < 0.01
                    ORDER BY id DESC LIMIT 1
                    """,
                    (workspace_id, movement["transaction_date"], movement["amount"]),
                ).fetchone()
            if scheduled_proof:
                status = "matched"
                reason = "Ya conciliado contra Casa y préstamo de papá programados; no se vuelve a registrar."
                counts[status] += 1
                _upsert_reconciliation_line(conn, user_id, workspace_id, statement_id, movement, status, matched_id, reason)
                continue

            original_currency = movement.get("original_currency")
            original_amount = movement.get("original_amount")
            rows = conn.execute(
                """
                SELECT id, description, transaction_type
                FROM transactions
                WHERE workspace_id = %s
                  AND transaction_date::date = %s::date
                  AND (
                      ABS(amount - %s) < 0.01
                      OR (%s = 'USD' AND original_currency = 'USD' AND ABS(original_amount - %s) < 0.01)
                  )
                  AND transaction_type = %s
                ORDER BY id
                """,
                (
                    workspace_id,
                    movement["transaction_date"],
                    movement["amount"],
                    original_currency,
                    original_amount,
                    movement["transaction_type"],
                ),
            ).fetchall()
            exact_description_rows = [row for row in rows if _plain(row["description"]) == _plain(movement["description"])]
            if len(exact_description_rows) == 1:
                rows = exact_description_rows
            if len(rows) == 1:
                status = "matched"
                matched_id = int(rows[0]["id"])
                reason = "Coincide exactamente por fecha y monto con Finanzas."
            elif len(rows) > 1:
                status = "ambiguous"
                reason = "Hay varias transacciones con la misma fecha y monto; requiere revisión."
            else:
                matched_id = _import_missing_statement_movement(
                    conn,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    statement_id=statement_id,
                    bank=bank,
                    movement=movement,
                )
                status = "matched"
                reason = "Faltaba en Finanzas y se agregó automáticamente desde el estado de cuenta verificado."
        counts[status] += 1
        _upsert_reconciliation_line(conn, user_id, workspace_id, statement_id, movement, status, matched_id, reason)
    final_status = "reconciled" if counts["missing"] == 0 and counts["ambiguous"] == 0 else "needs_review"
    conn.execute(
        "UPDATE email_statement_documents SET status = %s, updated_at = NOW() WHERE id = %s AND workspace_id = %s",
        (final_status, statement_id, workspace_id),
    )
    return {"status": "OK", "statement_id": statement_id, "movements": len(movements), "summary": counts, "reconciliation_status": final_status}


def _import_missing_statement_movement(
    conn,
    *,
    user_id: int,
    workspace_id: str,
    statement_id: int,
    bank: str,
    movement: dict[str, Any],
) -> int:
    """Import one authoritative statement row; the source marker makes retries idempotent."""
    if bank == "multimoney":
        source_marker = f"statement:{statement_id}:reference:{movement['reference']}"
    else:
        source_marker = (
            f"statement:{statement_id}:card:{movement.get('card_last4') or 'account'}:"
            f"reference:{movement['reference']}:date:{movement['transaction_date']}:"
            f"amount:{movement.get('original_amount') or movement['amount']}"
        )
    existing = conn.execute(
        """
        SELECT id
        FROM transactions
        WHERE workspace_id = %s
          AND source = %s
          AND notes LIKE %s
        ORDER BY id
        LIMIT 1
        """,
        (workspace_id, f"{bank}_statement", f"%{source_marker}%"),
    ).fetchone()
    if existing:
        return int(existing["id"])

    row = conn.execute(
        """
        INSERT INTO transactions (
            user_id, workspace_id, transaction_date, description, amount,
            transaction_type, category, account, source, notes,
            original_amount, original_currency, exchange_rate, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        (
            user_id,
            workspace_id,
            movement["transaction_date"],
            movement["description"],
            movement["amount"],
            movement["transaction_type"],
            movement["category"],
            "MultiMoney" if bank == "multimoney" else "BAC",
            f"{bank}_statement",
            f"Importado automáticamente durante conciliación mensual | {source_marker}",
            movement.get("original_amount"),
            movement.get("original_currency"),
            movement.get("exchange_rate"),
        ),
    ).fetchone()
    return int(row["id"])


def _upsert_reconciliation_line(conn, user_id, workspace_id, statement_id, movement, status, matched_id, reason) -> None:
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
