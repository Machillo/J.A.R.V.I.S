from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection


TRANSACTION_TYPES = {
    "income": "income",
    "expense": "expense",
    "debt_payment": "debt_payment",
    "transfer": "transfer",
    "investment": "investment",
    "investment_withdrawal": "investment_withdrawal",
    "loan_received": "loan_received",
    "loan_disbursement": "loan_received",
}


def _as_float(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sum_rows(rows, key):
    return sum(_as_float(row.get(key)) for row in rows)


def get_transaction_summary():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT transaction_type, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = %s
            GROUP BY transaction_type
            """,
            (user_id,)
        ).fetchall()

    totals = {
        "income": 0.0,
        "expenses": 0.0,
        "debt_payments": 0.0,
        "transfers": 0.0,
        "investments": 0.0,
        "investment_withdrawals": 0.0,
        "loan_received": 0.0,
    }

    for row in rows:
        tx_type = row["transaction_type"]
        total = _as_float(row["total"])

        if tx_type == "income":
            totals["income"] += total
        elif tx_type == "expense":
            totals["expenses"] += total
        elif tx_type == "debt_payment":
            totals["debt_payments"] += total
        elif tx_type == "transfer":
            totals["transfers"] += total
        elif tx_type == "investment":
            totals["investments"] += total
        elif tx_type == "investment_withdrawal":
            totals["investment_withdrawals"] += total
        elif tx_type in ("loan_received", "loan_disbursement"):
            totals["loan_received"] += total

    totals["net_from_transactions"] = (
        totals["income"]
        + totals["loan_received"]
        + totals["investment_withdrawals"]
        - totals["expenses"]
        - totals["debt_payments"]
        - totals["investments"]
    )

    return totals


def get_top_expense_categories(limit: int = 8):
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY category
            ORDER BY total DESC
            LIMIT %s
            """,
            (user_id, limit)
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_month():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT TO_CHAR(transaction_date, 'YYYY-MM') AS month,
                   COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY month
            ORDER BY month
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_monthly_flow():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                TO_CHAR(transaction_date, 'YYYY-MM') AS month,
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type = 'loan_received' THEN amount ELSE 0 END), 0) AS loan_received,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(CASE WHEN transaction_type = 'debt_payment' THEN amount ELSE 0 END), 0) AS debt_payments,
                COALESCE(SUM(CASE WHEN transaction_type = 'investment' THEN amount ELSE 0 END), 0) AS investments,
                COALESCE(SUM(CASE WHEN transaction_type = 'investment_withdrawal' THEN amount ELSE 0 END), 0) AS investment_withdrawals
            FROM transactions
            WHERE user_id = %s
            GROUP BY month
            ORDER BY month
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_current_month_summary():
    monthly_flow = get_monthly_flow()

    if not monthly_flow:
        return {
            "month": None,
            "income": 0.0,
            "loan_received": 0.0,
            "expenses": 0.0,
            "debt_payments": 0.0,
            "investments": 0.0,
            "available": 0.0,
        }

    current = dict(monthly_flow[-1])
    current["available"] = (
        _as_float(current.get("income"))
        + _as_float(current.get("loan_received"))
        + _as_float(current.get("investment_withdrawals"))
        - _as_float(current.get("expenses"))
        - _as_float(current.get("debt_payments"))
        - _as_float(current.get("investments"))
    )

    return current


def get_expenses_by_category_and_month():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                TO_CHAR(transaction_date, 'YYYY-MM') AS month,
                category,
                COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY month, category
            ORDER BY month, total DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_transaction_analysis():
    return {
        "summary": get_transaction_summary(),
        "current_month_summary": get_current_month_summary(),
        "monthly_flow": get_monthly_flow(),
        "top_expense_categories": get_top_expense_categories(),
        "expenses_by_month": get_expenses_by_month(),
        "expenses_by_category_and_month": get_expenses_by_category_and_month(),
    }
