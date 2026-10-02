"""Movements after a declared account balance: the one rule every balance consumer uses.

An account balance is declared at a moment (``account_balances.balance_as_of``). Its
current balance is that declared balance plus the cash effect of the account's linked
movements that happened *after* the declaration. Account balances, the reconciliation
that compares them, the month-end forecast that starts from them, and net worth all use
this module, so they always agree.

What decides "after":

- A movement's economic date (``transactions.transaction_date``) is authoritative.
  Its local day is compared with the declaration's local day:
  - earlier day: it was already part of the declared balance; no adjustment;
  - later day: it happened after the declaration; it adjusts the balance.
- Same local day: the economic date carries no time of day, so the order cannot be
  known from it. Only then is ``transactions.created_at`` used, as a tie-breaker: the
  movement counts as after the declaration when DINCR recorded it after the
  declaration moment.

``created_at`` is when DINCR created or imported the record. It is never the economic
date, and it is never rewritten to make balances agree: a January movement imported in
October stays created in October and still does not move a balance declared in
September.

The declaration's local day is taken in ``DECLARATION_TIMEZONE``. This is an explicit
fallback for every plan and account. The per-user ``users.timezone`` column holds a
signup placeholder, not a real choice, so it is not used. A real per-user, workspace or
account timezone is required before international expansion.
"""
from __future__ import annotations

import re

# Explicit, documented fallback (see module docstring). The only place it is defined.
DECLARATION_TIMEZONE = "America/Costa_Rica"

# Cash direction of a movement on its account. This is not its economic classification:
# loan proceeds (loan_received / loan_disbursement) put cash into the receiving account
# but are never income, and the liability lives in debts, never here. receivable_offset
# moves no cash. Own transfers / card payments keep their neutral treatment: a transfer
# is one row linked to one account, with no explicit origin and destination, so its two
# sides cannot be applied (docs/finance/account-balance-cash-effects.md).
CASH_IN_TYPES = ("income", "refund", "reimbursement", "receivable_payment", "asset_sale", "loan_received", "loan_disbursement")
CASH_OUT_TYPES = ("expense", "debt_payment")

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value + "'" for value in values)


def _alias(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError("invalid SQL alias")
    return name


def after_declaration_sql(tx: str = "t", account: str = "a") -> str:
    """SQL condition: movement ``tx`` happened after ``account``'s declared balance."""
    t, a = _alias(tx), _alias(account)
    declared_day = f"({a}.balance_as_of AT TIME ZONE '{DECLARATION_TIMEZONE}')::date"
    return (
        f"({t}.transaction_date > {declared_day}"
        f" OR ({t}.transaction_date = {declared_day} AND {t}.created_at > {a}.balance_as_of))"
    )


def cash_effect_sql(tx: str = "t") -> str:
    """SQL expression: signed cash effect of movement ``tx`` on its account."""
    t = _alias(tx)
    return (
        f"CASE WHEN {t}.transaction_type IN ({_sql_list(CASH_IN_TYPES)}) THEN {t}.amount"
        f" WHEN {t}.transaction_type IN ({_sql_list(CASH_OUT_TYPES)}) THEN -{t}.amount"
        " ELSE 0 END"
    )


def movements_since_declaration_sql(account: str = "a") -> str:
    """Subquery (for a LATERAL join or a scalar use) over ``account``'s movements after its
    declared balance: ``movement_count`` and ``movement_delta`` (signed cash effect)."""
    a = _alias(account)
    return (
        "SELECT COUNT(*) AS movement_count,"
        f" COALESCE(SUM({cash_effect_sql('t')}), 0) AS movement_delta"
        " FROM transactions t"
        f" WHERE t.workspace_id = {a}.workspace_id AND t.financial_account_id = {a}.id"
        f" AND {after_declaration_sql('t', a)}"
    )
