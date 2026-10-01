"""Who may have scheduled debt installments applied.

`service.apply_due_installments` records each due installment as paid (debt_payments,
a debt_payment transaction) and moves the debt's remaining_amount, installments_paid
and payment dates. It is an explicit command (POST /finance/debts/apply-due-installments,
dry run by default) and never runs from a read: listing debts, the cycle report,
Home, Strategy or an advisor never alter them.

- DINCR Owner creates debts through `add_debt` with an explicit schedule
  (start/first payment date, auto_update_monthly) and applies due installments
  with the command.
- DINCR Users never opt in: their debts change only through explicit writes
  (edit a debt, register a payment).
"""
from __future__ import annotations

from backend.auth.current_user import get_current_user


def schedule_automation_enabled() -> bool:
    try:
        return (get_current_user() or {}).get("role") == "owner"
    except Exception:  # no authenticated context (scripts, tests): never write
        return False
