from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime
from typing import Any


POPULAR_SENDER_MARKERS = (
    "@bancopopular.fi.cr",
    "@bancopopularinforma.fi.cr",
    "@bpdc.fi.cr",
)


def _plain(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().lower()


def is_popular_sender(sender: str | None) -> bool:
    clean = (sender or "").lower()
    return any(marker in clean for marker in POPULAR_SENDER_MARKERS)


def _label(text: str, label: str, next_labels: tuple[str, ...] = ()) -> str | None:
    def pattern(value: str) -> str:
        # PDF extraction frequently joins words ("delPago") or separates them
        # with arbitrary line breaks. Treat spaces inside known labels as optional.
        return r"\s*".join(re.escape(part) for part in value.split())

    stops = "|".join(pattern(item) for item in next_labels)
    suffix = rf"(?=\s+(?:{stops})\b|$)" if stops else r"(?=\n|$)"
    match = re.search(rf"{pattern(label)}\s*:?\s*(.+?){suffix}", text or "", re.I | re.S)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else None


def _money(value: str | None) -> float | None:
    raw = re.sub(r"[^\d,.-]", "", value or "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        head, tail = raw.rsplit(",", 1)
        raw = head.replace(",", "") + (f".{tail}" if len(tail) == 2 else tail)
    try:
        return float(raw)
    except ValueError:
        return None


def _date(value: str | None) -> str | None:
    match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", value or "")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _base_movement(received_at: str | None) -> dict[str, Any]:
    return {
        "bank": "popular",
        "email_kind": "movement",
        "source": "email_monitor",
        "received_at": received_at,
        "original_amount": None,
        "original_currency": None,
        "exchange_rate": None,
        "card_last4": None,
        "billing_cycle_start": None,
        "billing_cycle_end": None,
    }


def parse_popular_loan_payment(text: str, received_at: str | None = None) -> dict[str, Any] | None:
    plain = _plain(text)
    if "comprobante de pago de prestamos" not in plain and not (
        "numero de operacion" in plain and "amortizacion saldo" in plain
    ):
        return None

    labels = (
        "Saldo Anterior", "Amortización Saldo", "Intereses Corrientes",
        "Intereses de Mora", "Cargos por Pólizas", "Fracciones o Excesos",
        "Otros Cargos", "Nuevo Saldo", "Tasa Anual", "Medio de Pago",
        "Cuotas Pagadas", "Fecha Próximo Pago", "Días Atraso",
        "Cuotas Atraso", "Estado Operación",
    )
    amount = _money(_label(text, "Monto del Pago", labels))
    transaction_date = _date(_label(text, "Fecha Aplicación", ("Patrono", "Número Comprobante")))
    reference = _label(text, "Número Comprobante", ("Fecha Planilla", "Identificación del Cliente"))
    if not amount or not transaction_date or not reference:
        return None

    operation = _label(text, "Número de Operación", ("Fecha Aplicación",))
    amortization = _money(_label(text, "Amortización Saldo", labels))
    interest = _money(_label(text, "Intereses Corrientes", labels))
    late_interest = _money(_label(text, "Intereses de Mora", labels))
    insurance = _money(_label(text, "Cargos por Pólizas", labels))
    other_charges = _money(_label(text, "Otros Cargos", labels))
    new_balance = _money(_label(text, "Nuevo Saldo", labels))
    details = [
        f"amortización={amortization:.2f}" if amortization is not None else None,
        f"intereses={interest:.2f}" if interest is not None else None,
        f"mora={late_interest:.2f}" if late_interest is not None else None,
        f"pólizas={insurance:.2f}" if insurance is not None else None,
        f"otros={other_charges:.2f}" if other_charges is not None else None,
        f"saldo_nuevo={new_balance:.2f}" if new_balance is not None else None,
    ]
    return {
        **_base_movement(received_at),
        "transaction_date": transaction_date,
        "description": "Pago de préstamo Banco Popular",
        "amount": amount,
        "transaction_type": "expense",
        "category": "Banco Popular",
        "account": "Banco Popular · préstamo",
        "notes": " | ".join(item for item in details if item),
        "external_reference": reference,
        "loan_operation": operation,
        "loan_breakdown": {
            "principal": amortization,
            "interest": interest,
            "late_interest": late_interest,
            "insurance": insurance,
            "other_charges": other_charges,
            "new_balance": new_balance,
        },
        "dedupe_key": f"popular_loan_payment|{transaction_date}|{reference}|{amount:.2f}",
        # Payroll deductions can already be reflected in net salary. Always
        # require Kenneth's review before creating a direct expense.
        "confidence": 0.93,
        "confidence_reason": "Comprobante oficial de cuota Popular; requiere revisar posible rebajo de planilla.",
    }


def parse_popular_sinpe_receipt(text: str, received_at: str | None = None) -> dict[str, Any] | None:
    plain = _plain(text)
    if "transaccion sinpe" not in plain or "referencia sinpe" not in plain:
        return None
    status = _label(text, "Estado de la Transacción", ("Canal Origen", "Servicio SINPE"))
    if status and _plain(status) != "aplicada":
        return None
    amount = _money(_label(text, "Monto Enviado", ("Moneda", "Nombre del Producto")))
    transaction_date = _date(_label(text, "Fecha", ("Estado de la Transacción",)))
    reference = _label(text, "Referencia SINPE", ("Número Comprobante", "Fecha"))
    if not amount or not transaction_date or not reference:
        return None
    movement = _plain(_label(text, "Tipo de movimiento", ()) or "")
    outgoing = "debito" in movement
    description = _label(text, "Descripcion", ("Tipo de movimiento",)) or "Transferencia SINPE Banco Popular"
    return {
        **_base_movement(received_at),
        "transaction_date": transaction_date,
        "description": description[:240],
        "amount": amount,
        "transaction_type": "expense" if outgoing else "income",
        "category": "Transferencia",
        "account": "Banco Popular",
        "notes": f"SINPE Popular aplicado | referencia {reference}",
        "external_reference": reference,
        "dedupe_key": f"popular_sinpe|{transaction_date}|{reference}|{amount:.2f}|{'out' if outgoing else 'in'}",
        # Ownership resolution decides later whether this was a transfer
        # between the user's own accounts.
        "confidence": 0.92,
        "confidence_reason": "Comprobante SINPE oficial; pendiente confirmar contraparte o cuenta propia.",
    }


def parse_popular_loan_snapshot(text: str) -> dict[str, Any] | None:
    plain = _plain(text)
    if "estado de cuenta de operaciones de credito" not in plain:
        return None
    operation = _label(text, "ID Operación de crédito", ("Fecha de emisión", "Fecha formalización del crédito"))
    current_balance = _money(_label(text, "Saldo actual adeudado (no incluye intereses)", ("Monto principal atrasado", "Monto total del crédito")))
    next_payment = _date(_label(text, "Fecha del próximo pago", ("Fecha del último pago", "Tasa Anual")))
    if not operation:
        return None
    return {
        "document_type": "loan_statement",
        "bank": "popular",
        "operation": operation,
        "current_balance": current_balance,
        "next_payment_date": next_payment,
    }


def parse_popular_card_statement(text: str) -> list[dict[str, Any]]:
    plain = _plain(text)
    if "estado de cuenta de tarjeta de credito" not in plain:
        return []

    card_match = re.search(r"(?:n[uú]mero de cuenta[^\n]*|\*{4,})[^\d\n]*(\d{4,5})\b", text, re.I)
    card_last4 = card_match.group(1)[-4:] if card_match else None
    purchases = re.search(
        r"detalle\s+de\s+compras\s+del\s+per[ií]odo(?P<body>.*?)"
        r"total\s+de\s+compras\s+del\s+per[ií]odo",
        text or "",
        re.I | re.S,
    )
    if not purchases:
        return []
    movements: list[dict[str, Any]] = []
    # Popular exports table rows in either dd/mm/yyyy or dd-mm-yyyy form.
    row = re.compile(
        r"(?m)^\s*(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{4})\s+"
        r"(?P<description>[^\n]{3,180}?)\s+"
        r"(?P<crc>[\d.,]+)\s+(?P<usd>[\d.,]+)\s*$"
    )
    for match in row.finditer(purchases.group("body")):
        description = re.sub(r"\s+", " ", match.group("description")).strip()
        if _plain(description).startswith(("total ", "saldo anterior", "pago minimo")):
            continue
        crc = _money(match.group("crc")) or 0.0
        usd = _money(match.group("usd")) or 0.0
        if crc <= 0 and usd <= 0:
            continue
        # JARVIS stores its base amount in CRC. A Popular statement does not
        # provide a trustworthy conversion rate per row, so USD-only purchases
        # stay pending in the document instead of being imported with the wrong
        # currency value.
        if crc <= 0 and usd > 0:
            continue
        original_amount = crc
        identity = f"{match.group('date')}|{description}|{crc:.2f}"
        reference = f"popular-card-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]}"
        movements.append({
            "transaction_date": datetime.strptime(match.group("date").replace("-", "/"), "%d/%m/%Y").date().isoformat(),
            "reference": reference,
            "description": description,
            "debit": original_amount,
            "credit": 0.0,
            "amount": original_amount,
            "balance": None,
            "direction": "out",
            "transaction_type": "expense",
            "category": "Banco Popular",
            "ignored": False,
            "card_last4": card_last4,
            "original_amount": None,
            "original_currency": None,
        })
    return movements


def parse_popular_statement(text: str) -> list[dict[str, Any]]:
    # Loan statements are liability snapshots, not transaction ledgers. They
    # remain stored as documents and must never be converted into fake expenses.
    if parse_popular_loan_snapshot(text):
        return []
    return parse_popular_card_statement(text)


def parse_popular_email_document(
    *, subject: str, sender: str, body: str, attachment_text: str | None,
    received_at: str | None,
) -> dict[str, Any] | None:
    if not is_popular_sender(sender):
        return None
    document = (attachment_text or "").strip()
    if not document:
        return None
    return parse_popular_loan_payment(document, received_at) or parse_popular_sinpe_receipt(document, received_at)
