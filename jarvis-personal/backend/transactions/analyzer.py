from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from datetime import date, datetime
import calendar


LOAN_TYPES = ("loan_received", "loan_disbursement")
OUTFLOW_TYPES = ("expense", "debt_payment")


def get_transaction_summary():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        def get_total(transaction_type: str):
            return conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE transaction_type = %s
                AND workspace_id = %s
                """,
                (transaction_type, workspace_id),
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
            WHERE workspace_id = %s
            AND transaction_type IN ('loan_received', 'loan_disbursement')
            """,
            (workspace_id,),
        ).fetchone()["total"]

        total_transactions = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM transactions
            WHERE workspace_id = %s
            """,
            (workspace_id,),
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
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría') AS category,
                   SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND workspace_id = %s
            GROUP BY COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría')
            ORDER BY total DESC
            LIMIT %s
            """,
            (workspace_id, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_month():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT to_char(transaction_date, 'YYYY-MM') AS month, SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND workspace_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM')
            ORDER BY month
            """,
            (workspace_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_expenses_by_category_and_month():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                to_char(transaction_date, 'YYYY-MM') AS month,
                COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría') AS category,
                SUM(amount) AS total
            FROM transactions
            WHERE transaction_type = 'expense'
            AND workspace_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM'), COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría')
            ORDER BY month, total DESC
            """,
            (workspace_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_monthly_flow():
    """Return the monthly Analytics cash-flow series.

    Analytics answers a cash-flow question: how much money actually entered and
    left during each month.

    Inflows:
    - income (salary, bonuses, investment interest, etc.);
    - loan_received / loan_disbursement (cash received from financing);
    - receivable_payment (money paid back by people who owed the user).

    Expenses shown by Analytics:
    - expense (actual consumption/spending), net of refunds.

    Debt payments stay outside this monthly expense line. Debt scheduling and
    monthly installments are handled by the debt/Overview logic and must not
    inflate Analytics expenses. Loan disbursements still count as money received
    for the month without creating a second debt record.
    """
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                to_char(transaction_date, 'YYYY-MM') AS month,
                COALESCE(SUM(CASE
                    WHEN transaction_type IN ('income', 'loan_received', 'loan_disbursement', 'receivable_payment')
                    THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) AS earned_income,
                COALESCE(SUM(CASE WHEN transaction_type IN ('loan_received', 'loan_disbursement') THEN amount ELSE 0 END), 0) AS loan_received,
                COALESCE(SUM(CASE WHEN transaction_type = 'receivable_payment' THEN amount ELSE 0 END), 0) AS receivable_payments,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) AS gross_expenses,
                COALESCE(SUM(CASE WHEN transaction_type = 'refund' THEN amount ELSE 0 END), 0) AS refunds,
                COALESCE(SUM(CASE WHEN transaction_type = 'debt_payment' THEN amount ELSE 0 END), 0) AS debt_payments
            FROM transactions
            WHERE workspace_id = %s
            GROUP BY to_char(transaction_date, 'YYYY-MM')
            ORDER BY month
            """,
            (workspace_id,),
        ).fetchall()

    flow = []
    cumulative = 0.0
    for row in rows:
        item = dict(row)
        for key in (
            "income", "earned_income", "loan_received", "receivable_payments",
            "gross_expenses", "refunds", "debt_payments",
        ):
            item[key] = round(float(item.get(key) or 0), 2)

        # Refunds reverse consumption. Debt payments are intentionally NOT
        # added to Analytics expenses; debt installments are handled separately.
        item["spending"] = round(item["gross_expenses"] - item["refunds"], 2)
        item["expenses"] = item["spending"]
        item["outflow"] = item["expenses"]  # Backward-compatible alias.
        item["monthly_balance"] = round(item["income"] - item["expenses"], 2)
        cumulative = round(cumulative + item["monthly_balance"], 2)
        item["cumulative_balance"] = cumulative
        flow.append(item)

    return flow



def get_spending_breakdown():
    """Return YTD spending categories plus drill-down transactions.

    Spending is based on real ``expense`` transactions.  The house contribution
    is a special recurring cash expense in this personal finance setup: when a
    month is missing a materialized Casa transaction, the active fixed-expense
    schedule supplies that monthly occurrence so the spending view does not
    under-report Vivienda. Existing Casa transactions are never duplicated.
    """
    workspace_id = get_current_workspace_id()
    today = date.today()
    year_start = date(today.year, 1, 1)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, transaction_date, description, amount, transaction_type,
                   COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría') AS category,
                   source, notes
            FROM transactions
            WHERE workspace_id = %s
              AND transaction_type = 'expense'
              AND transaction_date::date BETWEEN %s::date AND %s::date
            ORDER BY transaction_date ASC, id ASC
            """,
            (workspace_id, year_start, today),
        ).fetchall()

        house = conn.execute(
            """
            SELECT id, name, category, expected_amount, frequency, interval_months,
                   start_month, due_day, is_active
            FROM fixed_expenses
            WHERE workspace_id = %s
              AND is_active = TRUE
              AND LOWER(TRIM(name)) = 'casa'
            ORDER BY id
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()

    items = []
    for row in rows:
        item = dict(row)
        item["amount"] = round(float(item.get("amount") or 0), 2)
        item["synthetic"] = False
        items.append(item)

    # Casa is known to be paid monthly. Fill only missing months; never replace
    # or duplicate a real transaction. This keeps YTD Vivienda complete while
    # preserving the transaction ledger as the primary source of truth.
    if house and float(house.get("expected_amount") or 0) > 0:
        expected = round(float(house["expected_amount"]), 2)
        house_category = house.get("category") or "Vivienda"

        real_house_months = set()
        for item in items:
            desc = str(item.get("description") or "").lower()
            category = str(item.get("category") or "").lower()
            if category == str(house_category).lower() or "casa" in desc:
                dt = item.get("transaction_date")
                if hasattr(dt, "strftime"):
                    real_house_months.add(dt.strftime("%Y-%m"))
                else:
                    real_house_months.add(str(dt)[:7])

        month = year_start
        while month <= today:
            month_key = month.strftime("%Y-%m")
            if month_key not in real_house_months:
                due_day = int(house.get("due_day") or 1)
                last_day = calendar.monthrange(month.year, month.month)[1]
                scheduled_date = date(month.year, month.month, min(due_day, last_day))
                # Casa is an explicitly confirmed monthly payment. For the current
                # month, show it in YTD even when its configured due day is later
                # than today; use today as the drill-down date instead of a future
                # date.
                synthetic_date = min(scheduled_date, today)
                items.append({
                        "id": f"fixed-casa-{month_key}",
                        "transaction_date": synthetic_date.isoformat(),
                        "description": "Casa",
                        "amount": expected,
                        "transaction_type": "expense",
                        "category": house_category,
                        "source": "fixed_expense_schedule",
                        "notes": "Gasto fijo mensual completado en Spending para evitar subregistro histórico.",
                        "synthetic": True,
                    })

            if month.month == 12:
                month = date(month.year + 1, 1, 1)
            else:
                month = date(month.year, month.month + 1, 1)

    items.sort(key=lambda item: (str(item.get("transaction_date") or ""), str(item.get("id") or "")))

    totals = {}
    for item in items:
        category = item.get("category") or "Sin categoría"
        totals.setdefault(category, {"category": category, "total": 0.0, "count": 0})
        totals[category]["total"] += float(item.get("amount") or 0)
        totals[category]["count"] += 1

    categories = sorted(totals.values(), key=lambda row: row["total"], reverse=True)
    for row in categories:
        row["total"] = round(row["total"], 2)

    return {
        "period": {"start": year_start.isoformat(), "end": today.isoformat(), "label": f"{today.year} YTD"},
        "total": round(sum(float(item.get("amount") or 0) for item in items), 2),
        "categories": categories,
        "transactions": items,
    }

def get_transaction_analysis():
    return {
        "summary": get_transaction_summary(),
        "top_expense_categories": get_top_expense_categories(),
        "expenses_by_month": get_expenses_by_month(),
        "expenses_by_category_and_month": get_expenses_by_category_and_month(),
        "monthly_flow": get_monthly_flow(),
        "spending_breakdown": get_spending_breakdown(),
    }
