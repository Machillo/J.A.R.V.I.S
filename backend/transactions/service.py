from backend.core.database import get_connection
from backend.auth.current_user import get_current_user_id


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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
            WHERE user_id = ?
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
            WHERE id = ?
            AND user_id = ?
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
            WHERE id = ?
            AND user_id = ?
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
            WHERE id = ?
            AND user_id = ?
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

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE id = ?
            AND user_id = ?
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
            AND user_id = ?
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