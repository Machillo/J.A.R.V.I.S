"""Money limits per column, from the NUMERIC types Labs verified (labs/schema/labs_schema.sql).

Limits differ per table: never assume one global maximum. All values are
Decimal; Labs never uses float for money.
"""
from __future__ import annotations

from decimal import Decimal


def numeric_max(precision: int, scale: int) -> Decimal:
    """Largest value a NUMERIC(precision, scale) column stores."""
    return Decimal(10) ** (precision - scale) - Decimal(1).scaleb(-scale)


def numeric_step(scale: int) -> Decimal:
    return Decimal(1).scaleb(-scale)


# (table, column) -> (precision, scale)
COLUMNS: dict[tuple[str, str], tuple[int, int]] = {
    ("transactions", "amount"): (12, 2),
    ("transactions", "original_amount"): (12, 2),
    ("transactions", "exchange_rate"): (12, 6),
    ("salaries", "amount"): (14, 2),
    ("salaries", "original_amount"): (14, 2),
    ("salaries", "exchange_rate"): (14, 6),
    ("expenses", "amount"): (14, 2),
    ("expenses", "original_amount"): (14, 2),
    ("expenses", "exchange_rate"): (14, 6),
    ("debts", "total_amount"): (14, 2),
    ("debts", "remaining_amount"): (14, 2),
    ("debts", "monthly_payment"): (14, 2),
    ("debts", "interest_rate"): (8, 4),
    ("debt_payments", "amount"): (14, 2),
    ("financial_goals", "target_amount"): (14, 2),
    ("financial_goals", "current_amount"): (14, 2),
    ("finva_budget_items", "monthly_limit"): (14, 2),
    ("finva_recurring_items", "amount"): (14, 2),
    ("exchange_rates", "exchange_rate"): (14, 6),
    ("account_balances", "current_balance"): (18, 2),
    ("finva_email_candidates", "amount"): (18, 2),
    ("finva_email_candidates", "original_amount"): (18, 2),
    ("finva_email_candidates", "confidence"): (5, 4),
}


def max_for(table: str, column: str) -> Decimal:
    return numeric_max(*COLUMNS[(table, column)])


def step_for(table: str, column: str) -> Decimal:
    return numeric_step(COLUMNS[(table, column)][1])


def overflow_for(table: str, column: str) -> Decimal:
    """The smallest value that no longer fits (max + one step)."""
    return max_for(table, column) + step_for(table, column)
