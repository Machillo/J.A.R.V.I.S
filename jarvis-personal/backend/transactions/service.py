from backend.core.database import get_connection
from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.finance.category_catalog import normalize_category


def _ensure_exchange_rates_table(conn):
    """Keep currency-rate persistence available even before schema migrations run."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 1,
            workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
            rate_date DATE NOT NULL,
            currency TEXT NOT NULL,
            exchange_rate NUMERIC(14, 6) NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (workspace_id, rate_date, currency)
        )
        """
    )


def _saved_exchange_rate(conn, workspace_id: str, transaction_date: str, currency: str = "USD"):
    _ensure_exchange_rates_table(conn)
    row = conn.execute(
        """
        SELECT exchange_rate
        FROM exchange_rates
        WHERE workspace_id = %s
          AND rate_date = %s::date
          AND UPPER(currency) = UPPER(%s)
        LIMIT 1
        """,
        (workspace_id, transaction_date, currency),
    ).fetchone()
    return float(row["exchange_rate"]) if row else None


def _save_exchange_rate(conn, user_id: int, workspace_id: str, transaction_date: str, rate: float, currency: str = "USD", source: str = "manual"):
    _ensure_exchange_rates_table(conn)
    conn.execute(
        """
        INSERT INTO exchange_rates (user_id, workspace_id, rate_date, currency, exchange_rate, source)
        VALUES (%s, %s, %s::date, UPPER(%s), %s, %s)
        ON CONFLICT (workspace_id, rate_date, currency)
        DO UPDATE SET workspace_id = EXCLUDED.workspace_id,
                      exchange_rate = EXCLUDED.exchange_rate,
                      source = EXCLUDED.source,
                      updated_at = NOW()
        """,
        (user_id, workspace_id, transaction_date, currency, rate, source),
    )


def _reuse_saved_rates(conn, workspace_id: str):
    """Apply already-known daily USD rates to old or newly inserted pending rows."""
    _ensure_exchange_rates_table(conn)
    conn.execute(
        """
        UPDATE transactions t
        SET exchange_rate = er.exchange_rate,
            amount = ROUND(t.original_amount * er.exchange_rate, 2)
        FROM exchange_rates er
        WHERE t.workspace_id = %s
          AND er.workspace_id = t.workspace_id
          AND er.rate_date = t.transaction_date::date
          AND UPPER(er.currency) = 'USD'
          AND UPPER(COALESCE(t.original_currency, '')) = 'USD'
          AND t.original_amount IS NOT NULL
          AND t.exchange_rate IS NULL
        """,
        (workspace_id,),
    )


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
    workspace_id = get_current_workspace_id()
    category = normalize_category(category, transaction_type)
    currency = (original_currency or "").upper()

    with get_connection() as conn:
        if currency == "USD" and original_amount is not None:
            if exchange_rate is None:
                exchange_rate = _saved_exchange_rate(conn, workspace_id, transaction_date, currency)
            if exchange_rate is not None:
                exchange_rate = float(exchange_rate)
                amount = round(float(original_amount) * exchange_rate, 2)
                _save_exchange_rate(conn, user_id, workspace_id, transaction_date, exchange_rate, currency, source="transaction")

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
                workspace_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
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
                user_id,
                workspace_id
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
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM transactions
            WHERE workspace_id = %s
            ORDER BY transaction_date DESC, id DESC
            """,
            (workspace_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_transaction(transaction_id: int):
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM transactions
            WHERE id = %s
            AND workspace_id = %s
            """,
            (transaction_id, workspace_id)
        ).fetchone()

    if not row:
        return {
            "status": "ERROR",
            "message": "Transacción no encontrada."
        }

    return dict(row)


def delete_transaction(transaction_id: int):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE id = %s
            AND workspace_id = %s
            """,
            (transaction_id, workspace_id)
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
            AND workspace_id = %s
            """,
            (transaction_id, workspace_id)
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
    workspace_id = get_current_workspace_id()
    category = normalize_category(category, transaction_type)

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE id = %s
            AND workspace_id = %s
            """,
            (transaction_id, workspace_id)
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
            AND workspace_id = %s
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
                workspace_id
            )
        )

        conn.commit()

    return get_transaction(transaction_id)

def get_currency_alerts():
    """Return every old/new USD transaction still missing a daily conversion rate."""
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        # First reuse any rate that was already saved for that date. This makes
        # historical imports and future inserts self-healing.
        _reuse_saved_rates(conn, workspace_id)
        conn.commit()

        rows = conn.execute(
            """
            SELECT id, transaction_date, description, amount, transaction_type,
                   category, original_amount, original_currency, exchange_rate
            FROM transactions
            WHERE workspace_id = %s
              AND UPPER(COALESCE(original_currency, '')) = 'USD'
              AND original_amount IS NOT NULL
              AND exchange_rate IS NULL
            ORDER BY transaction_date::date ASC, id ASC
            """,
            (workspace_id,),
        ).fetchall()

        saved_rows = conn.execute(
            """
            SELECT rate_date, currency, exchange_rate, source, updated_at
            FROM exchange_rates
            WHERE workspace_id = %s AND UPPER(currency) = 'USD'
            ORDER BY rate_date DESC
            """,
            (workspace_id,),
        ).fetchall()

    items = [dict(row) for row in rows]
    grouped = {}
    for item in items:
        day = str(item.get("transaction_date"))[:10]
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
        "saved_rates": [dict(row) for row in saved_rows],
    }


def apply_currency_rate(transaction_date: str, rate: float):
    """Persist one USD->CRC daily rate and apply it to all pending rows for that date."""
    rate = float(rate or 0)
    if rate <= 0:
        raise ValueError("El tipo de cambio debe ser mayor que cero.")

    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _save_exchange_rate(conn, user_id, workspace_id, transaction_date, rate, "USD", source="manual")

        rows = conn.execute(
            """
            SELECT id, original_amount
            FROM transactions
            WHERE workspace_id = %s
              AND transaction_date::date = %s::date
              AND UPPER(COALESCE(original_currency, '')) = 'USD'
              AND original_amount IS NOT NULL
              AND exchange_rate IS NULL
            ORDER BY id
            """,
            (workspace_id, transaction_date),
        ).fetchall()

        for row in rows:
            original = float(row["original_amount"] or 0)
            amount = round(original * rate, 2)
            conn.execute(
                """
                UPDATE transactions
                SET amount = %s, exchange_rate = %s
                WHERE id = %s AND workspace_id = %s
                """,
                (amount, rate, row["id"], workspace_id),
            )

        conn.commit()

    return {
        "date": str(transaction_date)[:10],
        "exchange_rate": rate,
        "updated": len(rows),
        "saved": True,
    }

