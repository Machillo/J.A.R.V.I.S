from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.service import get_financial_summary
from backend.goals.service import get_financial_goals


def get_expense_breakdown():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, expense_type, SUM(amount) AS total
            FROM expenses
            WHERE workspace_id = %s
            GROUP BY category, expense_type
            ORDER BY total DESC
            """,
            (workspace_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_debt_breakdown():
    workspace_id = get_current_workspace_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT name, debt_type, remaining_amount, monthly_payment, interest_rate
            FROM debts
            WHERE workspace_id = %s
            ORDER BY remaining_amount DESC
            """,
            (workspace_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def get_income_breakdown():
    summary = get_financial_summary()

    return {
        "projected_gross_income": summary["income"]["projected_gross_income"],
        "payroll_deductions_total": summary["income"]["payroll_deductions_total"],
        "projected_net_income": summary["income"]["projected_net_income"],
        "bonus_total": summary["income"]["bonus_total"],
        "total_income": summary["income"]["total_income"]
    }


def get_assets_breakdown():
    summary = get_financial_summary()

    return {
        "savings_total": summary["assets"]["savings_total"],
        "investments_total": summary["assets"]["investments_total"],
        "net_worth": summary["results"]["net_worth"]
    }


def build_report(period: str):
    summary = get_financial_summary()
    goals = get_financial_goals()

    return {
        "period": period,
        "summary": summary,
        "income": get_income_breakdown(),
        "expenses": {
            "total": summary["expenses"]["expenses_total"],
            "fixed": summary["expenses"]["fixed_expenses_total"],
            "variable": summary["expenses"]["variable_expenses_total"],
            "one_time": summary["expenses"]["one_time_expenses_total"],
            "by_category": get_expense_breakdown()
        },
        "debts": {
            "total": summary["debts"]["debt_total"],
            "monthly_payments": summary["debts"]["monthly_debt_payments"],
            "items": get_debt_breakdown()
        },
        "assets": get_assets_breakdown(),
        "goals": goals,
        "results": {
            "available_cash": summary["results"]["available_cash"],
            "net_worth": summary["results"]["net_worth"]
        }
    }


def get_weekly_report():
    return build_report("weekly")


def get_monthly_report():
    return build_report("monthly")


def get_annual_report():
    return build_report("annual")
