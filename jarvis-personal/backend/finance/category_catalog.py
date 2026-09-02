from __future__ import annotations

import re
from typing import Any

from backend.core.database import get_connection


OFFICIAL_CATEGORIES: list[dict[str, Any]] = [
    # Ingresos
    {"group_name": "INGRESOS", "category_name": "Salario", "transaction_type": "income", "sort_order": 10, "aliases": ["salario", "sueldo", "planilla", "pago semanal", "pago", "nomina", "nómina"]},
    {"group_name": "INGRESOS", "category_name": "Horas extra", "transaction_type": "income", "sort_order": 20, "aliases": ["horas extra", "hora extra", "ot", "overtime", "extra"]},
    {"group_name": "INGRESOS", "category_name": "Bono", "transaction_type": "income", "sort_order": 30, "aliases": ["bono", "bonus", "comision", "comisión"]},
    {"group_name": "INGRESOS", "category_name": "Reembolso", "transaction_type": "income", "sort_order": 40, "aliases": ["reembolso", "devolucion", "devolución", "refund"]},
    {"group_name": "INGRESOS", "category_name": "Inversión", "transaction_type": "income", "sort_order": 50, "aliases": ["dividendo", "dividendos", "interes", "interés", "ganancia inversion", "ganancia inversión"]},
    {"group_name": "INGRESOS", "category_name": "Otros ingresos", "transaction_type": "income", "sort_order": 60, "aliases": ["otros ingresos", "ingreso extra", "freelance", "venta"]},

    # Gastos fijos
    {"group_name": "GASTOS FIJOS", "category_name": "Vivienda", "transaction_type": "expense", "sort_order": 110, "aliases": ["alquiler", "renta", "casa", "vivienda", "hipoteca"]},
    {"group_name": "GASTOS FIJOS", "category_name": "Servicios", "transaction_type": "expense", "sort_order": 120, "aliases": ["servicios", "agua", "luz", "electricidad", "recibo", "aya", "cnfl", "ice electricidad"]},
    {"group_name": "GASTOS FIJOS", "category_name": "Internet", "transaction_type": "expense", "sort_order": 130, "aliases": ["internet", "wifi", "fibra", "kolbi", "telecable", "liberty"]},
    {"group_name": "GASTOS FIJOS", "category_name": "Teléfono", "transaction_type": "expense", "sort_order": 140, "aliases": ["telefono", "teléfono", "celular", "linea", "línea", "movil", "móvil"]},
    {"group_name": "GASTOS FIJOS", "category_name": "Seguros", "transaction_type": "expense", "sort_order": 150, "aliases": ["seguro", "seguros", "poliza", "póliza", "ins"]},

    # Gastos variables
    {"group_name": "GASTOS VARIABLES", "category_name": "Comida", "transaction_type": "expense", "sort_order": 210, "aliases": ["super", "supermercado", "comida", "maxi pali", "maxipalí", "walmart", "mas x menos", "automercado", "pali", "palí", "verduleria", "verdulería"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Restaurante", "transaction_type": "expense", "sort_order": 220, "aliases": ["restaurante", "uber eats", "ubereats", "comida rapida", "comida rápida", "mcdonald", "mcdonalds", "burger", "kfc", "pizza", "soda", "cafeteria", "cafetería"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Transporte", "transaction_type": "expense", "sort_order": 230, "aliases": ["uber", "didi", "taxi", "bus", "transporte", "peaje", "parqueo"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Gasolina", "transaction_type": "expense", "sort_order": 240, "aliases": ["gasolina", "combustible", "bomba", "estacion", "estación", "servicentro"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Entretenimiento", "transaction_type": "expense", "sort_order": 250, "aliases": ["cine", "netflix", "spotify", "playstation", "psn", "juego", "videojuego", "entretenimiento", "salida", "anime"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Compras", "transaction_type": "expense", "sort_order": 260, "aliases": ["compra", "compras", "amazon", "temu", "shein", "ropa", "zapatos", "tienda", "mall"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Salud", "transaction_type": "expense", "sort_order": 270, "aliases": ["salud", "farmacia", "medicina", "doctor", "medico", "médico", "clinica", "clínica", "dentista", "hospital"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Deporte", "transaction_type": "expense", "sort_order": 275, "aliases": ["deporte", "muay thai", "muaythai", "boxeo", "box", "artes marciales"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Servicios personales", "transaction_type": "expense", "sort_order": 278, "aliases": ["servicio personal", "servicios personales", "lavado de ropa", "lavar ropa", "lavanderia", "lavandería"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Mascotas", "transaction_type": "expense", "sort_order": 280, "aliases": ["mascota", "mascotas", "hamster", "hámster", "veterinaria", "vet", "alimento mascota"]},

    # Deudas
    {"group_name": "DEUDAS", "category_name": "Tarjeta BAC", "transaction_type": "expense", "sort_order": 310, "aliases": ["bac", "tarjeta bac", "visa bac", "mastercard bac"]},
    {"group_name": "DEUDAS", "category_name": "MultiMoney", "transaction_type": "expense", "sort_order": 320, "aliases": ["multimoney", "multi money"]},
    {"group_name": "DEUDAS", "category_name": "Banco Popular", "transaction_type": "expense", "sort_order": 330, "aliases": ["banco popular", "popular", "prestamo popular", "préstamo popular"]},
    {"group_name": "DEUDAS", "category_name": "Familiar", "transaction_type": "expense", "sort_order": 340, "aliases": ["familiar", "familia", "papa", "papá", "mama", "mamá"]},
    {"group_name": "DEUDAS", "category_name": "Otros préstamos", "transaction_type": "expense", "sort_order": 350, "aliases": ["prestamo", "préstamo", "credito", "crédito", "deuda"]},

    # Ahorro
    {"group_name": "AHORRO", "category_name": "Fondo emergencia", "transaction_type": "transfer", "sort_order": 410, "aliases": ["fondo emergencia", "emergencia", "fondo de emergencia"]},
    {"group_name": "AHORRO", "category_name": "Viajes", "transaction_type": "transfer", "sort_order": 420, "aliases": ["viaje", "viajes", "ecuador", "japon", "japón", "mexico", "méxico"]},
    {"group_name": "AHORRO", "category_name": "Meta personal", "transaction_type": "transfer", "sort_order": 430, "aliases": ["meta", "meta personal", "objetivo", "ahorro"]},

    # Inversiones
    {"group_name": "INVERSIONES", "category_name": "IBKR", "transaction_type": "transfer", "sort_order": 510, "aliases": ["ibkr", "interactive brokers", "acciones", "bolsa"]},
    {"group_name": "INVERSIONES", "category_name": "Cripto", "transaction_type": "transfer", "sort_order": 520, "aliases": ["cripto", "crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "sol"]},
    {"group_name": "INVERSIONES", "category_name": "Otros", "transaction_type": "transfer", "sort_order": 530, "aliases": ["otros", "otra inversion", "otra inversión"]},
]

_CATEGORY_BY_NORMALIZED_NAME = {
    item["category_name"].strip().lower(): item["category_name"]
    for item in OFFICIAL_CATEGORIES
}
_CATEGORY_TRANSACTION_TYPE = {
    item["category_name"]: item["transaction_type"]
    for item in OFFICIAL_CATEGORIES
}
_ALIAS_TO_CATEGORY: dict[str, str] = {}
for item in OFFICIAL_CATEGORIES:
    _ALIAS_TO_CATEGORY[item["category_name"].strip().lower()] = item["category_name"]
    for alias in item.get("aliases", []):
        _ALIAS_TO_CATEGORY[alias.strip().lower()] = item["category_name"]

DEFAULT_EXPENSE_CATEGORY = "Compras"
DEFAULT_INCOME_CATEGORY = "Otros ingresos"


def _category_matches_transaction_type(category: str, transaction_type: str | None) -> bool:
    if transaction_type == "income":
        return _CATEGORY_TRANSACTION_TYPE.get(category) == "income"
    if transaction_type in {"expense", "debt_payment"}:
        return _CATEGORY_TRANSACTION_TYPE.get(category) == "expense"
    return True


def _safe_category(category: str, transaction_type: str | None) -> str:
    if _category_matches_transaction_type(category, transaction_type):
        return category
    return DEFAULT_INCOME_CATEGORY if transaction_type == "income" else DEFAULT_EXPENSE_CATEGORY


def normalize_category(value: str | None, transaction_type: str | None = None) -> str:
    if not value:
        return DEFAULT_INCOME_CATEGORY if transaction_type == "income" else DEFAULT_EXPENSE_CATEGORY

    raw = value.strip()
    normalized = raw.lower()

    if normalized in _CATEGORY_BY_NORMALIZED_NAME:
        return _safe_category(_CATEGORY_BY_NORMALIZED_NAME[normalized], transaction_type)

    if normalized in _ALIAS_TO_CATEGORY:
        return _safe_category(_ALIAS_TO_CATEGORY[normalized], transaction_type)

    compact = re.sub(r"\s+", " ", normalized)
    if compact in _ALIAS_TO_CATEGORY:
        return _safe_category(_ALIAS_TO_CATEGORY[compact], transaction_type)

    for alias, category in _ALIAS_TO_CATEGORY.items():
        if alias and alias in compact:
            if _category_matches_transaction_type(category, transaction_type):
                return category

    return DEFAULT_INCOME_CATEGORY if transaction_type == "income" else DEFAULT_EXPENSE_CATEGORY


def expense_type_for_category(category: str) -> str:
    category = normalize_category(category, "expense")
    group = next(
        (item["group_name"] for item in OFFICIAL_CATEGORIES if item["category_name"] == category),
        "GASTOS VARIABLES",
    )
    if group == "GASTOS FIJOS":
        return "fixed"
    if group == "DEUDAS":
        return "fixed"
    return "variable"


def get_category_catalog() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id,
                   group_name,
                   category_name,
                   transaction_type,
                   aliases,
                   is_active,
                   sort_order
            FROM category_catalog
            WHERE is_active = TRUE
            ORDER BY sort_order ASC, group_name ASC, category_name ASC
            """
        ).fetchall()

    if rows:
        return [dict(row) for row in rows]

    return OFFICIAL_CATEGORIES


def get_category_groups() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in get_category_catalog():
        grouped.setdefault(item["group_name"], []).append(item["category_name"])
    return grouped
