import re
from pypdf import PdfReader
from backend.transactions.parser import detect_category


MONTHS = {
    "ENE": "01",
    "FEB": "02",
    "MAR": "03",
    "ABR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AGO": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DIC": "12",
}


def bac_date_to_iso(raw_date: str):
    day, month, year = raw_date.split("-")
    return f"20{year}-{MONTHS[month.upper()]}-{day.zfill(2)}"


def extract_pdf_text(file_path: str):
    reader = PdfReader(file_path)
    text = ""

    for page in reader.pages:
        text += page.extract_text() or ""
        text += "\n"

    return text


def parse_bac_credit_card_pdf(file_path: str, default_exchange_rate: float = 508.77):
    text = extract_pdf_text(file_path)

    transactions = []

    lines = text.splitlines()

    for line in lines:
        line = line.strip()

        # Ejemplo CRC:
        # 4-MAY-26 NOVO FIT CLUB_ SAN JOSE_ CRI CRC 24,950.00
        crc_match = re.search(
            r"(?P<date>\d{1,2}-[A-Z]{3}-\d{2})\s+"
            r"(?P<description>.+?)\s+CRC\s+"
            r"(?P<amount>[\d,]+\.\d{2})$",
            line
        )

        if crc_match:
            raw_date = crc_match.group("date")
            description = crc_match.group("description").strip()
            amount = float(crc_match.group("amount").replace(",", ""))

            # Ignorar pagos recibidos, notas y movimientos que no son compra
            ignored_keywords = [
                "PAGO RECIBIDO",
                "SALDO ANTERIOR",
                "TRASLADO A MINICUOTAS",
            ]

            if any(keyword.lower() in description.lower() for keyword in ignored_keywords):
                continue

            transactions.append({
                "transaction_date": bac_date_to_iso(raw_date),
                "description": clean_description(description),
                "amount": amount,
                "transaction_type": "expense",
                "category": detect_category(description),
                "account": "BAC",
                "source": "bac_pdf",
                "notes": "Importado desde PDF BAC"
            })

            continue

        # Ejemplo USD:
        # 16-MAY-26 PLAYSTATION_ SAN MATEO_ USA USD 11.99
        usd_match = re.search(
            r"(?P<date>\d{1,2}-[A-Z]{3}-\d{2})\s+"
            r"(?P<description>.+?)\s+USD\s+"
            r"(?P<amount>[\d,]+\.\d{2})$",
            line
        )

        if usd_match:
            raw_date = usd_match.group("date")
            description = usd_match.group("description").strip()
            original_amount = float(usd_match.group("amount").replace(",", ""))
            amount_crc = round(original_amount * default_exchange_rate, 2)

            transactions.append({
                "transaction_date": bac_date_to_iso(raw_date),
                "description": clean_description(description),
                "amount": amount_crc,
                "transaction_type": "expense",
                "category": detect_category(description),
                "account": "BAC",
                "source": "bac_pdf",
                "notes": "Compra en dólares importada desde PDF BAC",
                "original_amount": original_amount,
                "original_currency": "USD",
                "exchange_rate": default_exchange_rate
            })

    return {
        "source": "BAC PDF",
        "total_detected": len(transactions),
        "transactions": transactions
    }


def clean_description(description: str):
    description = description.replace("_", " ")
    description = re.sub(r"\s+", " ", description)
    return description.strip()