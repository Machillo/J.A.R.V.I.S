from backend.core.database import get_connection


def get_transaction_summary():
    with get_connection() as conn:
        def get_total(transaction_type: str):
            return conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE transaction_type = %s
                """,
                (transaction_type,)
            ).fetchone()["total"]

        total_income = get_total("income")
        total_expenses = get_total("expense")
        total_debt_payments = get_total("debt_payment")
        total_transfers = get_total("transfer")
        total_investments = get_total("investment")
        total_investment_withdrawals = get_total("investment_withdrawal")
        total_loan_disbursements = get_total("loan_disbursement")

    return {
        "income": total_income,
        "expenses": total_expenses,
        "debt_payments": total_debt_payments,
        "transfers": total_transfers,
        "investments": total_investments,
        "investment_withdrawals": total_investment_withdrawals,
        "loan_disbursements": total_loan_disbursements,
        "net_from_transactions": total_income - total_expenses - total_debt_payments
    }


def get_top_expense_categories(limit: int = 5):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            GROUP BY category
            ORDER BY total DESC
            LIMIT %s
            """,
            (limit,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_month():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT substr(transaction_date, 1, 7) AS month, SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            GROUP BY month
            ORDER BY month
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_category_and_month():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT 
                substr(transaction_date, 1, 7) AS month,
                category,
                SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            GROUP BY month, category
            ORDER BY month, total DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_transaction_analysis():
    return {
        "summary": get_transaction_summary(),
        "top_expense_categories": get_top_expense_categories(),
        "expenses_by_month": get_expenses_by_month(),
        "expenses_by_category_and_month": get_expenses_by_category_and_month()
    }