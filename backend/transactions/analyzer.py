from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection


def _as_number(value):
    return float(value or 0)


def get_transaction_summary():
    user_id = get_current_user_id()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(CASE WHEN transaction_type = 'debt_payment' THEN amount ELSE 0 END), 0) AS debt_payments,
                COALESCE(SUM(CASE WHEN transaction_type IN ('loan_received', 'loan_disbursement') THEN amount ELSE 0 END), 0) AS loans_received,
                COALESCE(SUM(CASE WHEN transaction_type IN ('investment', 'saving') THEN amount ELSE 0 END), 0) AS investments,
                COALESCE(SUM(CASE WHEN transaction_type = 'transfer' THEN amount ELSE 0 END), 0) AS transfers
            FROM transactions
            WHERE user_id = %s
            """,
            (user_id,)
        ).fetchone()

    income = _as_number(row["income"])
    expenses = _as_number(row["expenses"])
    debt_payments = _as_number(row["debt_payments"])
    loans_received = _as_number(row["loans_received"])
    investments = _as_number(row["investments"])

    return {
        "income": income,
        "expenses": expenses,
        "debt_payments": debt_payments,
        "loans_received": loans_received,
        "loan_disbursements": loans_received,
        "transfers": _as_number(row["transfers"]),
        "investments": investments,
        "net_cashflow": income + loans_received - expenses - debt_payments - investments,
        "net_from_transactions": income - expenses - debt_payments,
    }


def get_top_expense_categories(limit: int = 8):
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(category, ''), 'Sin categoría') AS category,
                   COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY COALESCE(NULLIF(category, ''), 'Sin categoría')
            ORDER BY total DESC
            LIMIT %s
            """,
            (user_id, limit)
        ).fetchall()

    return [dict(row) for row in rows]


def get_monthly_flow():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                to_char(transaction_date, 'YYYY-MM') AS month,
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type IN ('loan_received', 'loan_disbursement') THEN amount ELSE 0 END), 0) AS loans_received,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(CASE WHEN transaction_type = 'debt_payment' THEN amount ELSE 0 END), 0) AS debt_payments
            FROM transactions
            WHERE user_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM')
            ORDER BY month
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_month():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT to_char(transaction_date, 'YYYY-MM') AS month,
                   COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM')
            ORDER BY month
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_category_and_month():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                to_char(transaction_date, 'YYYY-MM') AS month,
                COALESCE(NULLIF(category, ''), 'Sin categoría') AS category,
                COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM'), COALESCE(NULLIF(category, ''), 'Sin categoría')
            ORDER BY month, total DESC
            """,
            (user_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_transaction_analysis():
    monthly_flow = get_monthly_flow()
    latest_month = monthly_flow[-1] if monthly_flow else None

    return {
        "summary": get_transaction_summary(),
        "latest_month": latest_month,
        "monthly_flow": monthly_flow,
        "top_expense_categories": get_top_expense_categories(),
        "expenses_by_month": get_expenses_by_month(),
        "expenses_by_category_and_month": get_expenses_by_category_and_month(),
    }
