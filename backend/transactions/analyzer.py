from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection
from datetime import date, datetime
import calendar


LOAN_TYPES = ("loan_received", "loan_disbursement")
OUTFLOW_TYPES = ("expense", "debt_payment")


def get_transaction_summary():
    user_id = get_current_user_id()

    with get_connection() as conn:
        def get_total(transaction_type: str):
            return conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE transaction_type = %s
                AND user_id = %s
                """,
                (transaction_type, user_id),
            ).fetchone()["total"]

        total_income = get_total("income")
        total_expenses = get_total("expense")
        total_debt_payments = get_total("debt_payment")
        total_transfers = get_total("transfer")
        total_investments = get_total("investment")
        total_investment_withdrawals = get_total("investment_withdrawal")

        total_loan_received = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = %s
            AND transaction_type IN ('loan_received', 'loan_disbursement')
            """,
            (user_id,),
        ).fetchone()["total"]

        total_transactions = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM transactions
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()["total"]

    return {
        "income": total_income,
        "expenses": total_expenses,
        "debt_payments": total_debt_payments,
        "transfers": total_transfers,
        "investments": total_investments,
        "investment_withdrawals": total_investment_withdrawals,
        "loan_disbursements": total_loan_received,
        "loan_received": total_loan_received,
        "net_from_transactions": total_income + total_loan_received - total_expenses - total_debt_payments,
        "total_transactions": total_transactions,
    }


def get_top_expense_categories(limit: int = 8):
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría') AS category,
                   SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría')
            ORDER BY total DESC
            LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_month():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT to_char(transaction_date, 'YYYY-MM') AS month, SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM')
            ORDER BY month
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_category_and_month():
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                to_char(transaction_date, 'YYYY-MM') AS month,
                COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría') AS category,
                SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND user_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM'), COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría')
            ORDER BY month, total DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_monthly_flow():
    """Return the monthly Analytics series.

    This chart measures financial performance, not cash movements or debt service:
    - income: only transactions explicitly classified as ``income``;
    - expenses: only ``expense`` transactions, net of ``refund`` transactions;
    - debt payments, transfers and loan disbursements stay outside the chart;
    - cumulative_balance carries only each month's income-minus-expenses result.

    Debt balances and debt payments remain available elsewhere in Finance, but they
    must never inflate the monthly expense line in Analytics.
    """
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                to_char(transaction_date, 'YYYY-MM') AS month,
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) AS gross_expenses,
                COALESCE(SUM(CASE WHEN transaction_type = 'refund' THEN amount ELSE 0 END), 0) AS refunds,
                COALESCE(SUM(CASE WHEN transaction_type = 'debt_payment' THEN amount ELSE 0 END), 0) AS debt_payments
            FROM transactions
            WHERE user_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM')
            ORDER BY month
            """,
            (user_id,),
        ).fetchall()

    flow = []
    cumulative = 0.0
    for row in rows:
        item = dict(row)
        item["income"] = round(float(item.get("income") or 0), 2)
        item["gross_expenses"] = round(float(item.get("gross_expenses") or 0), 2)
        item["refunds"] = round(float(item.get("refunds") or 0), 2)
        item["debt_payments"] = round(float(item.get("debt_payments") or 0), 2)

        # Analytics expense is consumption/spending for the month. A refund reverses
        # part of that spending; debt service is intentionally not added here.
        item["expenses"] = round(item["gross_expenses"] - item["refunds"], 2)
        item["outflow"] = item["expenses"]  # Backward-compatible alias for older clients.
        item["monthly_balance"] = round(item["income"] - item["expenses"], 2)
        cumulative = round(cumulative + item["monthly_balance"], 2)
        item["cumulative_balance"] = cumulative
        flow.append(item)

    return flow


def get_transaction_analysis():
    return {
        "summary": get_transaction_summary(),
        "top_expense_categories": get_top_expense_categories(),
        "expenses_by_month": get_expenses_by_month(),
        "expenses_by_category_and_month": get_expenses_by_category_and_month(),
        "monthly_flow": get_monthly_flow(),
    }
