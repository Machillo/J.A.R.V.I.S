from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any


PAYROLL_TERMS = ("salario", "planilla", "nomina", "nómina", "pago salarial")


def _plain(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def identify_received_payroll(parsed: dict[str, Any], *, subject: str, body: str) -> dict[str, Any]:
    """Mark only an applied bank credit with explicit payroll language as received salary."""
    if str(parsed.get("transaction_type") or "") != "income":
        return parsed
    text = _plain("\n".join((subject or "", body or "", str(parsed.get("description") or ""))))
    if "orden patronal" in text or not any(_plain(term) in text for term in PAYROLL_TERMS):
        return parsed
    if any(term in text for term in ("esperado", "proyectado", "estimado", "pendiente de pago")):
        return parsed
    enriched = dict(parsed)
    enriched.update({
        "category": "Salario",
        "movement_kind": "payroll_deposit",
        "payroll_received": True,
        "confidence_reason": "Depósito salarial aplicado: ingreso bancario con referencia explícita a salario/planilla/nómina.",
    })
    return enriched


def _period_month(value: Any) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m")
    match = re.match(r"^(20\d{2})-(0[1-9]|1[0-2])", str(value or ""))
    return f"{match.group(1)}-{match.group(2)}" if match else None


def link_received_payroll(conn, *, candidate_id: int, candidate: dict[str, Any], workspace_id: str) -> bool:
    """Link confirmed evidence without turning the CCSS reported salary into cash received."""
    if candidate.get("movement_kind") != "payroll_deposit" or not candidate.get("raw_payload", {}).get("payroll_received"):
        return False
    period = _period_month(candidate.get("transaction_date"))
    if not period:
        return False
    row = conn.execute(
        """UPDATE payroll_salary_reports
              SET payment_status='received',received_candidate_id=%s,received_at=%s::date,updated_at=NOW()
            WHERE workspace_id=%s AND period_month=%s
              AND (received_candidate_id IS NULL OR received_candidate_id=%s)
            RETURNING id""",
        (candidate_id, candidate.get("transaction_date"), workspace_id, period, candidate_id),
    ).fetchone()
    return bool(row)
