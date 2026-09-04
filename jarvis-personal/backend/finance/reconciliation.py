"""Account reconciliation report and explicit, user-confirmed correction."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.intelligence import _ensure_account_tables, list_account_balances


def _num(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def get_financial_reconciliation() -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    accounts = list_account_balances().get("items", [])
    details = []
    for account in accounts:
        if account.get("read_only") or account.get("account_type") == "investment":
            continue
        expected = _num(account.get("calculated_balance"))
        real = _num(account.get("current_balance"))
        difference = round(real - expected, 2)
        details.append({
            "account_id": account.get("id"), "account_name": account.get("account_name"),
            "institution": account.get("bank_name"), "last4": account.get("account_last4"),
            "currency": account.get("currency") or "CRC", "expected_balance": expected,
            "real_balance": real, "difference": difference,
            "movements_since_balance": int(account.get("movements_since_balance") or 0),
            "balance_as_of": account.get("balance_as_of"),
            "status": "ok" if abs(difference) < 0.01 else "needs_review",
        })

    with get_connection() as conn:
        unlinked = conn.execute(
            """SELECT id, transaction_date, description, amount, transaction_type, category, account
               FROM transactions WHERE workspace_id=%s AND financial_account_id IS NULL
               ORDER BY transaction_date DESC, id DESC LIMIT 100""", (workspace_id,)
        ).fetchall()
        duplicate_rows = conn.execute(
            """SELECT transaction_date, amount, LOWER(BTRIM(description)) AS description, COUNT(*) AS count,
                      ARRAY_AGG(id ORDER BY id) AS transaction_ids
               FROM transactions WHERE workspace_id=%s
               GROUP BY transaction_date, amount, LOWER(BTRIM(description))
               HAVING COUNT(*) > 1 ORDER BY MAX(transaction_date) DESC LIMIT 50""", (workspace_id,)
        ).fetchall()

    discrepancies = [item for item in details if item["status"] != "ok"]
    return {
        "status": "OK", "generated_at": datetime.utcnow().isoformat() + "Z",
        "accounts": details, "discrepancies": discrepancies,
        "unlinked_transactions": [dict(row) for row in unlinked],
        "possible_duplicates": [dict(row) for row in duplicate_rows],
        "summary": {"accounts": len(details), "needs_review": len(discrepancies), "unlinked": len(unlinked), "possible_duplicates": len(duplicate_rows)},
        "note": "JARVIS solo detecta y propone revisión. Ningún movimiento se borra, duplica o corrige automáticamente.",
    }


def confirm_account_reconciliation(account_id: int, real_balance: float, note: str = "") -> dict[str, Any]:
    """Store a new explicit balance snapshot only after user confirmation."""
    workspace_id = get_current_workspace_id()
    user_id = get_current_user_id()
    with get_connection() as conn:
        _ensure_account_tables(conn)
        row = conn.execute("SELECT * FROM account_balances WHERE id=%s AND workspace_id=%s AND COALESCE(is_active,TRUE)=TRUE", (account_id, workspace_id)).fetchone()
        if not row:
            raise ValueError("Cuenta financiera no encontrada.")
        conn.execute("UPDATE account_balances SET current_balance=%s, balance_as_of=NOW(), last_reconciliation_difference=0, updated_at=NOW() WHERE id=%s AND workspace_id=%s", (real_balance, account_id, workspace_id))
        conn.execute("INSERT INTO account_balance_history(user_id,workspace_id,financial_account_id,balance,currency,source,note) VALUES(%s,%s,%s,%s,%s,'confirmed_reconciliation',%s)", (user_id, workspace_id, account_id, real_balance, row.get("currency") or "CRC", note or "Saldo confirmado por el usuario."))
        conn.commit()
    return {"status": "OK", "account_id": account_id, "real_balance": round(float(real_balance), 2), "confirmed": True}
