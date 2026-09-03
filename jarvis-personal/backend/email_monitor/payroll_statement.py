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
    verifier = re.search(r"codigo verificador[^:]*:\s*([a-z0-9-]+)", plain, re.IGNORECASE)
    return {
        "period_month": f"{year:04d}-{MONTHS[month_name]:02d}",
        "trans_previous_salary": _money(row.group(3)),
        "previous_salary": _money(row.group(4)),
        "reported_salary": _money(row.group(5)),
        "daily_subsidy": _money(row.group(6)),
        "employer_number": employer.group(1) if employer else None,
        "verification_code": verifier.group(1).upper() if verifier else None,
    }
