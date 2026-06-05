import re

from datetime import date
from backend.finance.category_catalog import normalize_category
from backend.transactions.service import create_transaction

CATEGORY_RULES = {
        "Vivienda": [
        "casa",
        "alquiler",
        "hipoteca",
        "condominio",
        "vivienda"
    ],
    
    "Alimentación": [
        "walmart",
        "mas x menos",
        "automercado",
        "price smart",
        "pricesmart",
        "pali",
        "am pm",
        "fresh market",
        "megasuper",
        "supermercado",
        "discom",
        "pulperia",
        "abastecedor"
    ],

    "Restaurantes": [
        "mcdonald",
        "burger king",
        "kfc",
        "pizza hut",
        "subway",
        "taco bell",
        "uber eats",
        "dlc*uber eats",
        "bar y restaurante",
        "granizados",
        "didi food"
    ],

    "Transporte": [
        "uber rides",
        "dl*uber rides",
        "uber",
        "didi"
    ],

    "Gasolina": [
        "gasolinera",
        "delta",
        "uno",
        "texaco",
        "servicentro"
    ],

    "Gym": [
        "novo fit",
        "smart fit",
        "gym",
        "multi spa"
    ],

    "Deporte": [
        "uno sport",
        "box",
        "deportes",
        "sport"
    ],

    "Streaming": [
        "spotify",
        "netflix",
        "disney",
        "crunchyroll",
        "youtube"
    ],

    "Videojuegos": [
        "playstation",
        "playstationnetwork",
        "steam",
        "nintendo",
        "xbox",
        "gossip harbor",
        "kingshot",
        "8 ball pool",
        "google 8 ball",
        "google kingshot",
        "google gossip"
    ],

    "Educación": [
        "yousician",
        "duolingo",
        "udemy",
        "coursera",
        "platzi",
        "budge smart"
    ],

    "Tecnología": [
        "google one",
        "icloud",
        "apple",
        "chatgpt",
        "openai"
    ],

    "Compras Personales": [
        "reycomcell",
        "temu",
        "aliss",
        "amazon",
        "mercado libre",
        "shein",
        "siman",
        "universal"
    ],

    "Servicios": [
        "liberty",
        "kolbi",
        "ice",
        "claro",
        "movistar",
        "ayA",
        "cnfl",
        "jasec"
    ],

    "Seguros": [
        "seguro",
        "proteccion de ingr"
    ],

    "Pago Deuda": [
        "pago",
        "cuota",
        "prestamo",
        "préstamo"
    ],

    "Transferencia": [
        "sinpe",
        "dtr",
        "transferencia"
    ],

    "Inversión": [
        "inversion",
        "inversi",
        "ibkr",
        "interactive brokers"
    ],

    "Ingresos": [
        "planilla",
        "salario",
        "bono",
        "aguinaldo"
    ]
}


def detect_category(text: str):
    text = text.lower()

    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in text:
                return normalize_category(category, "expense")

    return normalize_category(text, "expense")


def extract_amount(text: str):
    match = re.search(
        r'₡\s?([\d,]+(?:\.\d+)?)',
        text
    )

    if match:
        return float(
            match.group(1)
            .replace(",", "")
        )

    return 0


def parse_transaction_text(text: str):
    amount = extract_amount(text)
    category = detect_category(text)

    return {
        "transaction_type": "expense",
        "amount": amount,
        "category": category,
        "description": text,
        "source": "parsed_text"
    }

def parse_and_save_transaction_text(text: str):
    parsed = parse_transaction_text(text)

    transaction = create_transaction(
        transaction_date=str(date.today()),
        description=parsed["description"],
        amount=parsed["amount"],
        transaction_type=parsed["transaction_type"],
        category=parsed["category"],
        account="BAC",
        source=parsed["source"],
        notes="Creado desde parser"
    )

    return {
        "message": "Transacción parseada y guardada correctamente.",
        "parsed": parsed,
        "transaction": transaction
    }