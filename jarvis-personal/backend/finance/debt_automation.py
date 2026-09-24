"""Who may have scheduled debt installments applied automatically.

`_sync_automatic_debt_payments` records each due installment as paid (debt_payments,
a debt_payment transaction) and rewrites the debt's remaining_amount,
installments_paid and payment dates. It runs from read paths (get_debts, the cycle
report), so it must only act where that automation was configured on purpose:

- DINCR Owner creates debts through `add_debt` with an explicit schedule
  (start/first payment date, auto_update_monthly) and relies on it.
- DINCR Users never opt in: their debts change only through explicit writes
  (edit a debt, register a payment). Opening Home, Strategy or an advisor must
  never alter them.
"""
from __future__ import annotations

from backend.auth.current_user import get_current_user


def schedule_automation_enabled() -> bool:
    try:
        return (get_current_user() or {}).get("role") == "owner"
    except Exception:  # no authenticated context (scripts, tests): never write
        return False
