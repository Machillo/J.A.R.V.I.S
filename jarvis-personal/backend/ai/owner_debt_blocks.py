"""The Owner's next locked savings block for a debt (GET /jarvis/premium/debt-savings-blocks).

Owner only: it reads the Owner's own strategy (``strategy_dashboard``), salary rule
(``owner_ledger.owner_salary``) and Salvavidas plan, and hands plain numbers to the neutral engine
``finance/debt_savings_blocks.py``. Read-only: every source only reads, scoped by the workspace.

- Safe monthly attack: the strategy's monthly debt attack from the base net salary (no overtime,
  bonus or VGH), minus the Salvavidas automatic contributions the attack would have to fund (they
  come out of the other shares first, as ``owner_commitments.absorb`` does for the cycle).
- Probable monthly attack: the safe one plus the attack's share of what the last
  ``AVERAGE_MONTHS`` closed months paid above the base salary (overtime and bonus are not fixed,
  but they help). Used only for the term, never for the weekly amount.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from backend.ai import owner_debt_block_store
from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.core.time import costa_rica_today
from backend.finance import debt_savings_blocks, salvavidas_plan
from backend.finance.service import get_debts
from backend.user_product.owner_ledger import owner_salary

AVERAGE_MONTHS = 3
MONTHLY_FACTOR = {"weekly": 52 / 12, "biweekly": 26 / 12, "monthly": 1.0}


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def automatic_savings_monthly(salvavidas: dict[str, Any], today: date) -> float:
    """The Salvavidas automatic contributions as a monthly amount (0 without an active plan)."""
    plan = salvavidas_plan.normalize_plan((salvavidas or {}).get("auto_contribution"))
    if not plan or not plan["enabled"] or (plan["end_date"] and date.fromisoformat(plan["end_date"]) < today):
        return 0.0
    return round(plan["amount"] * MONTHLY_FACTOR[plan["frequency"]], 2)


def safe_attack(attack: float, surplus: float, automatic: float) -> float:
    """The attack left after the automatic savings take the surplus's other shares first."""
    others = max(surplus - attack, 0.0)
    return round(max(attack - max(automatic - others, 0.0), 0.0), 2)


def average_income(workspace_id: str, today: date) -> tuple[float | None, bool]:
    """The salary of the last closed months by the Owner's salary rule, per month, and whether any of
    them is an estimate. None when no month has a salary."""
    end = today.replace(day=1)
    start = debt_savings_blocks.add_months(end, -AVERAGE_MONTHS)
    with get_connection() as conn:
        salary = owner_salary(conn, workspace_id, start, end)
    total = _f(salary["salary"])
    return (round(total / AVERAGE_MONTHS, 2) if total > 0 else None), bool(salary["closed_estimated"])


def get_owner_debt_savings_blocks() -> dict[str, Any]:
    from backend.ai import strategy_dashboard  # the Owner's strategy (imports this package)

    today = costa_rica_today()
    blueprint = strategy_dashboard._owner_strategy_blueprint()
    base_income = _f(blueprint.get("recurring_monthly_income"))
    surplus = _f(blueprint.get("base_estimated_extra_cash"))
    attack = _f(blueprint.get("recurring_debt_attack_extra"))
    automatic = automatic_savings_monthly(blueprint.get("salvavidas") or {}, today)
    safe = safe_attack(attack, surplus, automatic)

    warnings = []
    average, estimated = average_income(get_current_workspace_id(), today)
    if average is None:
        warnings.append("average_income_unknown")
    elif estimated:
        warnings.append("average_income_estimated")
    share = attack / surplus if surplus > 0 else 0.0
    probable = safe + max((average or base_income) - base_income, 0.0) * share

    debts = [debt for debt in (get_debts() or []) if _f(debt.get("remaining_amount")) > 0.01]
    order, _, _ = strategy_dashboard._simulate_debt_cascade(
        debts, recurring_monthly_extra=probable, first_month_extra=0.0, owner_rules=True)
    if any(debt.get("interest_rate") is None for debt in debts):
        warnings.append("interest_rate_unknown")
    blocks = owner_debt_block_store.stored_blocks()
    running = owner_debt_block_store.active(blocks, today)
    result = debt_savings_blocks.propose(
        today=today, safe_monthly_attack=safe, probable_monthly_attack=probable, debts=order, warnings=warnings,
        committed_weekly=owner_debt_block_store.weekly_committed(blocks, today),
        blocked_debt_ids={block["debt_id"] for block in running})
    return {**result, "automatic_savings_monthly": automatic, "average_monthly_income": average,
            "base_monthly_income": round(base_income, 2),
            "blocks": [owner_debt_block_store.with_progress(block, today) for block in owner_debt_block_store.open_blocks(blocks)]}
