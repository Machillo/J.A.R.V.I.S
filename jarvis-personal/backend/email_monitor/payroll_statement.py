from __future__ import annotations

import re
import unicodedata
from typing import Any

MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _money(value: str) -> float:
    return round(float((value or "0").replace(",", "")), 2)


def parse_ccss_order_patronal(subject: str, sender: str, text: str) -> dict[str, Any] | None:
    """Extrae el salario Actual de una Orden Patronal Digital de la CCSS.

    Mantener este parser en un módulo versionado evita depender de servicios
    externos durante el arranque de FastAPI.
    """
    combined = "\n".join([subject or "", sender or "", text or ""])
    plain = _plain(combined)
    if "orden patronal digital" not in plain:
        return None
    if "caja costarricense de seguro social" not in plain and "ccss" not in plain:
        return None

    amount = r"([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})"
    row = re.search(
        rf"\b({'|'.join(MONTHS)})\s+(20\d{{2}})\s+{amount}\s+{amount}\s+{amount}\s+{amount}",
        plain,
        re.IGNORECASE,
    )
    if not row:
        return None

    month_name, year = row.group(1).lower(), int(row.group(2))
    employer = re.search(r"\b(\d-\d{11}-\d{3}-\d{3})\b", combined)
    # Bounded gap: an unbounded [^:]* rescans the rest of the text at every match start.
    verifier = re.search(r"codigo verificador[^:\n]{0,40}:\s*([a-z0-9-]{1,64})", plain, re.IGNORECASE)
    return {
        "period_month": f"{year:04d}-{MONTHS[month_name]:02d}",
        "trans_previous_salary": _money(row.group(3)),
        "previous_salary": _money(row.group(4)),
        "reported_salary": _money(row.group(5)),
        "daily_subsidy": _money(row.group(6)),
        "employer_number": employer.group(1) if employer else None,
        "verification_code": verifier.group(1).upper() if verifier else None,
    }


# ---------------------------------------------------------------------------------------------
# Weekly / periodic payroll receipts ("comprobante de pago" sent by an employer's payroll system).
#
# A receipt is evidence of what the salary was made of; it is NOT a movement. The money is the
# bank deposit of the net amount, which a receipt only explains. So this parser never produces a
# transaction, and every deduction (social security, association, any loan repaid through payroll)
# is informational: the deducted money never reached the account, and a loan repaid this way is a
# debt the user already tracks. Recognized by structure, never by employer, sender or person.

_RECEIPT_PERIOD = re.compile(r"periodo:?\s*(\d{4,8})?\s*del\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})")
_RECEIPT_ROW = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*[¢₡]?\s*(?P<amount>-?[\d,]+\.\d{2})\s*\|\s*$")
_RECEIPT_HOURS = re.compile(r"\((?P<hours>[\d.]+)\s*horas?\)")


def _receipt_date(value: str) -> str:
    return f"{value[6:10]}-{value[3:5]}-{value[0:2]}"


def _income_kind(label: str) -> str:
    if "extra" in label or re.search(r"\bot\d?\b", label):
        return "overtime"
    if "feriado" in label:
        return "holiday_worked" if "trabajad" in label else "holiday_paid"
    if "vacacion" in label:
        return "vacation"
    if "aguinaldo" in label:
        return "aguinaldo"
    if re.search(r"bono|bonific|incentiv|comision|premio", label):
        return "bonus"
    if re.search(r"incapacidad|subsidio", label):
        return "sick_leave"
    if re.search(r"regular|ordinari|salario base", label):
        return "ordinary"
    return "other"


def _deduction_kind(label: str) -> str:
    if "ccss" in label or "seguro social" in label:
        return "social_security"
    if re.search(r"renta|impuesto", label):
        return "income_tax"
    if "embargo" in label or "pension alimentaria" in label:
        return "garnishment"
    if "prestamo" in label or "credito" in label:
        return "loan_repayment"
    if re.search(r"asociacion|solidarista|aporte obrero|aseco|cooperativa", label):
        return "association"
    return "other"


def parse_payroll_receipt(text: str) -> dict[str, Any] | None:
    """Gross, deductions and net of a payroll receipt, with each line classified.

    Returns None when the text is not a receipt. ``consistent`` is False (and the receipt
    needs review) when its lines do not add up to its own totals; nothing is estimated.
    """
    plain = _plain(text)
    period = _RECEIPT_PERIOD.search(plain)
    if not period or "neto a pagar" not in plain or not re.search(r"comprobante de pago|recibo de pago", plain):
        return None
    section, income, deductions = None, [], []
    for line in (text or "").splitlines():
        row_plain = _plain(line).strip()
        if "<<ingresos>>" in row_plain:
            section = "income"; continue
        if "<<descuentos>>" in row_plain:
            section = "deductions"; continue
        if "total ingresos" in row_plain or "<<base>>" in row_plain:
            section = None
        row = _RECEIPT_ROW.match(line.strip())
        if not row or not section:
            continue
        label = _plain(row.group("label"))
        hours = _RECEIPT_HOURS.search(label)
        item = {"label": row.group("label").strip(), "amount": _money(row.group("amount")),
                "hours": float(hours.group("hours")) if hours else None}
        if section == "income":
            income.append({**item, "kind": _income_kind(label)})
        else:
            deductions.append({**item, "kind": _deduction_kind(label), "creates_movement": False})

    def total(label: str) -> float | None:
        found = re.search(label + r":?\s*\|?\s*[¢₡]?\s*([\d,]+\.\d{2})", plain)
        return _money(found.group(1)) if found else None

    gross, deducted, net = total("total ingresos"), total("total descuentos"), total("neto a pagar")
    issued = re.search(r"fecha emision:?\s*(\d{2}/\d{2}/\d{4})", plain)
    consistent = (
        None not in (gross, deducted, net)
        and abs(sum(i["amount"] for i in income) - gross) <= 0.01
        and abs(sum(d["amount"] for d in deductions) - deducted) <= 0.01
        and abs(gross - deducted - net) <= 0.01
    )
    return {
        "kind": "payroll_receipt",
        "period_code": period.group(1),
        "period_start": _receipt_date(period.group(2)),
        "period_end": _receipt_date(period.group(3)),
        "issue_date": _receipt_date(issued.group(1)) if issued else None,
        "gross": gross,
        "deductions_total": deducted,
        "net": net,
        "income_lines": income,
        "deduction_lines": deductions,
        "consistent": consistent,
        "needs_review": not consistent or any(i["kind"] == "other" for i in income + deductions),
    }
