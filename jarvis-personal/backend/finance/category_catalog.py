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
    {"group_name": "GASTOS VARIABLES", "category_name": "Entretenimiento", "transaction_type": "expense", "sort_order": 250, "aliases": ["cine", "playstation", "psn", "juego", "videojuego", "entretenimiento", "salida", "anime"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Suscripciones", "transaction_type": "expense", "sort_order": 255, "aliases": ["suscripcion", "suscripción", "suscripciones", "subscription", "streaming", "netflix", "spotify"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Compras", "transaction_type": "expense", "sort_order": 260, "aliases": ["compra", "compras", "amazon", "temu", "shein", "ropa", "zapatos", "tienda", "mall"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Salud", "transaction_type": "expense", "sort_order": 270, "aliases": ["salud", "farmacia", "medicina", "doctor", "medico", "médico", "clinica", "clínica", "dentista", "hospital"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Deporte", "transaction_type": "expense", "sort_order": 275, "aliases": ["deporte", "muay thai", "muaythai", "boxeo", "box", "artes marciales"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Servicios personales", "transaction_type": "expense", "sort_order": 278, "aliases": ["servicio personal", "servicios personales", "lavado de ropa", "lavar ropa", "lavanderia", "lavandería"]},
    # Spending while travelling (flights, lodging, tours). Distinct from the "Viajes"
    # savings goal below: a trip is paid with this category, saved for with that one.
    {"group_name": "GASTOS VARIABLES", "category_name": "Viajes y turismo", "transaction_type": "expense", "sort_order": 279, "aliases": ["viaje", "viajes", "vuelo", "vuelos", "aerolinea", "aerolínea", "boleto aereo", "boleto aéreo", "hotel", "hospedaje", "alojamiento", "airbnb", "tour", "tours", "turismo"]},
    {"group_name": "GASTOS VARIABLES", "category_name": "Mascotas", "transaction_type": "expense", "sort_order": 280, "aliases": ["mascota", "mascotas", "hamster", "hámster", "veterinaria", "vet", "alimento mascota"]},

    # An expense whose category is not known yet. Explicit, so an unknown never hides
    # inside a real category ("Compras").
    {"group_name": "SIN CLASIFICAR", "category_name": "Sin categoría", "transaction_type": "expense", "sort_order": 290, "aliases": ["sin categoria", "sin categoría", "desconocido", "unknown"]},

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

    # Cobros y ventas: money that comes in without being earned income.
    # A collection reduces what someone owes; an asset sale turns an owned thing into cash.
    {"group_name": "COBROS Y VENTAS", "category_name": "Cuentas por cobrar", "transaction_type": "receivable_payment", "sort_order": 450, "aliases": ["cuentas por cobrar", "cobro", "cobros"]},
    {"group_name": "COBROS Y VENTAS", "category_name": "Venta de activo", "transaction_type": "asset_sale", "sort_order": 460, "aliases": ["venta de activo", "venta de bien", "venta de vehiculo", "venta de vehículo"]},

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
# One alias may belong to categories of different types ("viajes": the savings goal and
# travel spending); the transaction type decides which one applies.
_ALIAS_TO_CATEGORIES: dict[str, list[str]] = {}
for item in OFFICIAL_CATEGORIES:
    for alias in [item["category_name"], *item.get("aliases", [])]:
        names = _ALIAS_TO_CATEGORIES.setdefault(alias.strip().lower(), [])
        if item["category_name"] not in names:
            names.append(item["category_name"])
_ALIAS_TO_CATEGORY: dict[str, str] = {alias: names[0] for alias, names in _ALIAS_TO_CATEGORIES.items()}

# Unknown is a category of its own: never a silent "Compras".
UNKNOWN_EXPENSE_CATEGORY = "Sin categoría"
DEFAULT_EXPENSE_CATEGORY = UNKNOWN_EXPENSE_CATEGORY
DEFAULT_INCOME_CATEGORY = "Otros ingresos"


# A collection or an asset sale takes only its own category, never an income or expense one.
_OWN_CATEGORY_TYPE = {"receivable_payment": "receivable_payment", "receivable_offset": "receivable_payment", "asset_sale": "asset_sale"}


def _category_matches_transaction_type(category: str, transaction_type: str | None) -> bool:
    if transaction_type in _OWN_CATEGORY_TYPE:
        return _CATEGORY_TRANSACTION_TYPE.get(category) == _OWN_CATEGORY_TYPE[transaction_type]
    if transaction_type == "income":
        return _CATEGORY_TRANSACTION_TYPE.get(category) == "income"
    if transaction_type in {"expense", "debt_payment"}:
        return _CATEGORY_TRANSACTION_TYPE.get(category) == "expense"
    return True


# Settling a receivable and selling an asset have their own categories; every other
# non-income movement without a known category is explicitly "Sin categoría".
_TYPE_DEFAULT_CATEGORY = {"receivable_payment": "Cuentas por cobrar", "receivable_offset": "Cuentas por cobrar", "asset_sale": "Venta de activo"}


def default_category(transaction_type: str | None) -> str:
    if transaction_type == "income":
        return DEFAULT_INCOME_CATEGORY
    return _TYPE_DEFAULT_CATEGORY.get(transaction_type or "", DEFAULT_EXPENSE_CATEGORY)


def manual_expense_category(value: str | None) -> str:
    """The category of a manual expense as typed; empty or the API placeholder "general" is unknown, never Compras."""
    clean = str(value or "").strip()
    return UNKNOWN_EXPENSE_CATEGORY if clean.lower() in {"", "general"} else clean


def _safe_category(category: str, transaction_type: str | None) -> str:
    if _category_matches_transaction_type(category, transaction_type):
        return category
    return default_category(transaction_type)


def _compatible(names: list[str], transaction_type: str | None) -> str | None:
    """First category of the transaction's own type, else the first compatible one."""
    exact = next((name for name in names if _CATEGORY_TRANSACTION_TYPE.get(name) == transaction_type), None)
    return exact or next((name for name in names if _category_matches_transaction_type(name, transaction_type)), None)


def normalize_category(value: str | None, transaction_type: str | None = None) -> str:
    if not value:
        return default_category(transaction_type)

    raw = value.strip()
    normalized = raw.lower()

    compact = re.sub(r"\s+", " ", normalized)
    for key in (normalized, compact):
        exact_name = _CATEGORY_BY_NORMALIZED_NAME.get(key)
        if exact_name and _category_matches_transaction_type(exact_name, transaction_type):
            return exact_name
        if key in _ALIAS_TO_CATEGORIES:
            # A name or alias shared across types resolves to the one matching the transaction.
            return _compatible(_ALIAS_TO_CATEGORIES[key], transaction_type) or _safe_category(_ALIAS_TO_CATEGORIES[key][0], transaction_type)

    # Whole words only: a short alias ("ot", "ins", "box") must not match inside another word.
    for alias, names in _ALIAS_TO_CATEGORIES.items():
        if alias and re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", compact):
            category = _compatible(names, transaction_type)
            if category:
                return category

    return default_category(transaction_type)


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
