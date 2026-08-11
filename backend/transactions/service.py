from backend.core.database import get_connection
from backend.auth.current_user import get_current_user_id
from backend.finance.category_catalog import normalize_category


def create_transaction(
    transaction_date: str,
    description: str,
    amount: float,
    transaction_type: str,
    category: str,
    account: str = "",
    source: str = "manual",
    notes: str = "",
    original_amount: float | None = None,
    original_currency: str | None = None,
    exchange_rate: float | None = None
):
    user_id = get_current_user_id()
    category = normalize_category(category, transaction_type)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO transactions (
                transaction_date,
                description,
                amount,
                transaction_type,
                category,
                account,
                source,
                notes,
                original_amount,
                original_currency,
                exchange_rate,
                user_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                transaction_date,
                description,
                amount,
                transaction_type,
                category,
                account,
                source,
                notes,
                original_amount,
                original_currency,
                exchange_rate,
                user_id
            )
        )

        conn.commit()

    return {
        "message": "Transacción registrada correctamente.",
        "id": cursor.lastrowid,
        "user_id": user_id
    }


def get_transactions():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM transactions
            WHERE user_id = %s
            ORDER BY transaction_date DESC, id DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_transaction(transaction_id: int):
    user_id = get_current_user_id()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM transactions
            WHERE id = %s
            AND user_id = %s
            """,
            (transaction_id, user_id)
        ).fetchone()

    if not row:
        return {
            "status": "ERROR",
            "message": "Transacción no encontrada."
        }

    return dict(row)


def delete_transaction(transaction_id: int):
    user_id = get_current_user_id()

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE id = %s
            AND user_id = %s
            """,
            (transaction_id, user_id)
        ).fetchone()

        if not existing:
            return {
                "status": "ERROR",
                "message": "Transacción no encontrada o no pertenece al usuario actual."
            }

        conn.execute(
            """
            DELETE FROM transactions
            WHERE id = %s
            AND user_id = %s
            """,
            (transaction_id, user_id)
        )

        conn.commit()

    return {
        "message": "Transacción eliminada correctamente."
    }


def bulk_create_transactions(transactions: list[dict]):
    created = []

    for transaction in transactions:
        result = create_transaction(
            transaction_date=transaction["transaction_date"],
            description=transaction["description"],
            amount=transaction["amount"],
            transaction_type=transaction["transaction_type"],
            category=transaction["category"],
            account=transaction.get("account", ""),
            source=transaction.get("source", "manual"),
            notes=transaction.get("notes", ""),
            original_amount=transaction.get("original_amount"),
            original_currency=transaction.get("original_currency"),
            exchange_rate=transaction.get("exchange_rate")
        )

        created.append(result)

    return {
        "message": "Importación completada.",
        "total_created": len(created),
        "created": created
    }


def update_transaction(
    transaction_id: int,
    transaction_date: str,
    description: str,
    amount: float,
    transaction_type: str,
    category: str,
    account: str = "",
    source: str = "manual",
    notes: str = "",
    original_amount: float | None = None,
    original_currency: str | None = None,
    exchange_rate: float | None = None
):
    user_id = get_current_user_id()
    category = normalize_category(category, transaction_type)

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE id = %s
            AND user_id = %s
            """,
            (transaction_id, user_id)
        ).fetchone()

        if not existing:
            return {
                "status": "ERROR",
                "message": "Transacción no encontrada o no pertenece al usuario actual."
            }

        conn.execute(
            """
            UPDATE transactions
            SET transaction_date = %s,
                description = %s,
                amount = %s,
                transaction_type = %s,
                category = %s,
                account = %s,
                source = %s,
                notes = %s,
                original_amount = %s,
                original_currency = %s,
                exchange_rate = %s
            WHERE id = %s
            AND user_id = %s
            """,
            (
                transaction_date,
                description,
                amount,
                transaction_type,
                category,
                account,
                source,
                notes,
                original_amount,
                original_currency,
                exchange_rate,
                transaction_id,
                user_id
            )
        )

        conn.commit()

    return get_transaction(transaction_id)

def get_currency_alerts():
    """Return USD transactions that still need a conversion rate."""
    user_id = get_current_user_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, transaction_date, description, amount, transaction_type,
                   category, original_amount, original_currency, exchange_rate
            FROM transactions
            WHERE user_id = %s
              AND UPPER(COALESCE(original_currency, '')) = 'USD'
              AND exchange_rate IS NULL
            ORDER BY transaction_date ASC, id ASC
            """,
            (user_id,),
        ).fetchall()

    items = [dict(row) for row in rows]
    grouped = {}
    for item in items:
        day = str(item.get('transaction_date'))[:10]
        grouped.setdefault(day, []).append(item)

    return {
        "total": len(items),
        "dates": [
            {
                "date": day,
                "count": len(day_items),
                "total_usd": round(sum(float(x.get("original_amount") or 0) for x in day_items), 2),
                "items": day_items,
            }
            for day, day_items in grouped.items()
        ],
    }


def apply_currency_rate(transaction_date: str, rate: float):
    """Apply one manual USD->CRC rate to every pending USD transaction on a date."""
    rate = float(rate or 0)
    if rate <= 0:
        raise ValueError("El tipo de cambio debe ser mayor que cero.")

    user_id = get_current_user_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, original_amount
            FROM transactions
            WHERE user_id = %s
              AND transaction_date::date = %s::date
              AND UPPER(COALESCE(original_currency, '')) = 'USD'
              AND exchange_rate IS NULL
            ORDER BY id
            """,
            (user_id, transaction_date),
        ).fetchall()

        for row in rows:
            original = float(row["original_amount"] or 0)
            amount = round(original * rate, 2)
            conn.execute(
                """
                UPDATE transactions
                SET amount = %s, exchange_rate = %s
                WHERE id = %s AND user_id = %s
                """,
                (amount, rate, row["id"], user_id),
            )

        conn.commit()

    return {
        "date": str(transaction_date)[:10],
        "exchange_rate": rate,
        "updated": len(rows),
    }
