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
    """Monthly cash flow plus an estimated month-end debt balance.

    Debt history becomes exact as JARVIS records debt_payments. For older months that
    pre-date the amortization ledger, the balance is the best reconstruction available
    from the current balance and principal payments recorded after each month-end.
    """
    user_id = get_current_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                to_char(transaction_date, 'YYYY-MM') AS month,
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type IN ('loan_received', 'loan_disbursement') THEN amount ELSE 0 END), 0) AS loans,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(CASE WHEN transaction_type = 'debt_payment' THEN amount ELSE 0 END), 0) AS debt_payments
            FROM transactions
            WHERE user_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM')
            ORDER BY month
            """,
            (user_id,),
        ).fetchall()

        debts = [dict(row) for row in conn.execute(
            """
            SELECT id, total_amount, remaining_amount, start_date, created_at
            FROM debts
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()]

        payments = [dict(row) for row in conn.execute(
            """
            SELECT debt_id, payment_date, COALESCE(principal_amount, 0) AS principal_amount
            FROM debt_payments
            WHERE user_id = %s
              AND payment_date IS NOT NULL
            ORDER BY payment_date
            """,
            (user_id,),
        ).fetchall()]

    payments_by_debt = {}
    for payment in payments:
        payments_by_debt.setdefault(int(payment["debt_id"]), []).append(payment)

    def as_date(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.fromisoformat(str(value)[:10]).date()
        except (TypeError, ValueError):
            return None

    def debt_balance_at(month_end):
        total = 0.0
        for debt in debts:
            started = as_date(debt.get("start_date")) or as_date(debt.get("created_at"))
            if started and started > month_end:
                continue
            current = float(debt.get("remaining_amount") or 0)
            later_principal = sum(
                float(payment.get("principal_amount") or 0)
                for payment in payments_by_debt.get(int(debt["id"]), [])
                if as_date(payment.get("payment_date")) and as_date(payment.get("payment_date")) > month_end
            )
            reconstructed = max(current + later_principal, 0.0)
            original = float(debt.get("total_amount") or 0)
            if original > 0:
                reconstructed = min(reconstructed, original)
            total += reconstructed
        return round(total, 2)

    flow = []
    cumulative = 0.0
    for row in rows:
        item = dict(row)
        item["income"] = float(item.get("income") or 0)
        item["loans"] = float(item.get("loans") or 0)
        item["expenses"] = float(item.get("expenses") or 0)
        item["debt_payments"] = float(item.get("debt_payments") or 0)
        item["outflow"] = item["expenses"] + item["debt_payments"]
        item["net_flow"] = item["income"] + item["loans"] - item["outflow"]
        cumulative += item["net_flow"]
        item["cumulative_balance"] = round(cumulative, 2)

        year, month = map(int, item["month"].split("-"))
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        item["debt_balance"] = debt_balance_at(month_end)
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
