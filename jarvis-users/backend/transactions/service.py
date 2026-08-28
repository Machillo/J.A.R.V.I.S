from fastapi import HTTPException

from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection


def get_transactions():
    user_id = get_current_user_id()
    with get_connection() as conn:
        return conn.execute(
            """SELECT id, transaction_date, description, amount, transaction_type, category, notes, created_at
               FROM transactions WHERE user_id=%s ORDER BY transaction_date DESC, id DESC""",
            (user_id,),
        ).fetchall()


def create_transaction(**payload):
    user_id = get_current_user_id()
    if payload["transaction_type"] not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="transaction_type debe ser 'income' o 'expense'.")
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO transactions (user_id, transaction_date, description, amount, transaction_type, category, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               RETURNING id, transaction_date, description, amount, transaction_type, category, notes, created_at""",
            (user_id, payload["transaction_date"], payload["description"], payload["amount"],
             payload["transaction_type"], payload["category"], payload.get("notes", "")),
        ).fetchone()
        conn.commit()
    return row


def update_transaction(transaction_id: int, **payload):
    user_id = get_current_user_id()
    if payload["transaction_type"] not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="transaction_type debe ser 'income' o 'expense'.")
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE transactions SET transaction_date=%s, description=%s, amount=%s, transaction_type=%s,
                      category=%s, notes=%s
               WHERE id=%s AND user_id=%s
               RETURNING id, transaction_date, description, amount, transaction_type, category, notes, created_at""",
            (payload["transaction_date"], payload["description"], payload["amount"], payload["transaction_type"],
             payload["category"], payload.get("notes", ""), transaction_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transacción no encontrada.")
        conn.commit()
    return row


def delete_transaction(transaction_id: int):
    user_id = get_current_user_id()
    with get_connection() as conn:
        result = conn.execute("DELETE FROM transactions WHERE id=%s AND user_id=%s", (transaction_id, user_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transacción no encontrada.")
        conn.commit()
    return {"status": "ok"}
