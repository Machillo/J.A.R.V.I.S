from backend.core.database import get_connection


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
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
                exchange_rate
            )
        )

        conn.commit()

    return {
        "message": "Transacción registrada correctamente.",
        "id": cursor.lastrowid
    }


def get_transactions():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM transactions
            ORDER BY transaction_date DESC, id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_transaction(transaction_id: int):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM transactions
            WHERE id = ?
            """,
            (transaction_id,)
        ).fetchone()

    if not row:
        return {
            "status": "ERROR",
            "message": "Transacción no encontrada."
        }

    return dict(row)


def delete_transaction(transaction_id: int):
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM transactions
            WHERE id = ?
            """,
            (transaction_id,)
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
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE id = ?
            """,
            (transaction_id,)
        ).fetchone()

        if not existing:
            return {
                "status": "ERROR",
                "message": "Transacción no encontrada."
            }

        conn.execute(
            """
            UPDATE transactions
            SET transaction_date = ?,
                description = ?,
                amount = ?,
                transaction_type = ?,
                category = ?,
                account = ?,
                source = ?,
                notes = ?,
                original_amount = ?,
                original_currency = ?,
                exchange_rate = ?
            WHERE id = ?
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
                transaction_id
            )
        )

        conn.commit()

    return get_transaction(transaction_id)