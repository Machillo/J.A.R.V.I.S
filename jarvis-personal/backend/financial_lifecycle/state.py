"""Canonical DINCR financial state for longitudinal Phase 2 analysis."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from backend.advisor.core import build_advisor_strategy
from backend.auth.current_user import get_current_workspace_id
from backend.core.i18n import DEFAULT_LANGUAGE, use_language
from backend.finance.deterioration import get_financial_deterioration
from backend.finance.emergency_fund import get_salvavidas_state
from backend.finance.intelligence import get_real_availability, list_account_balances
from backend.finance.service import get_debts
from backend.finance.strategic_engine import get_monthly_financial_flow


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _monthly_ledger(flow: dict[str, Any]) -> dict[str, float]:
    current = date.today().strftime("%Y-%m")
    months = flow.get("months") or []
    row = next((item for item in reversed(months) if item.get("month") == current), None)
    if not row:
        row = months[-1] if months else {}
    return {
        "income": round(_n(row.get("income")), 2),
        "expenses": round(_n(row.get("expenses")), 2),
        "debt_payments": round(_n(row.get("debt_payments")), 2),
        "net_operational": round(_n(row.get("net_operational")), 2),
    }


def build_financial_state() -> dict[str, Any]:
    """Build one read-only state from canonical finance services.

    This function deliberately calls Advisor Core with persist=False. Phase 2A
    observes the strategy; it does not create strategy-history side effects.
    The state is persisted and compared across snapshots, so any text in it is
    kept in canonical Spanish; responses localize it when presenting.
    """
    with use_language(DEFAULT_LANGUAGE):
        return _build_financial_state()


def _build_financial_state() -> dict[str, Any]:
    strategy = build_advisor_strategy(persist=False)
    accounts = list_account_balances().get("items") or []
    debts = [item for item in (get_debts() or []) if _n(item.get("remaining_amount")) > 0]
    salvavidas = get_salvavidas_state()
    availability = get_real_availability()
    deterioration = get_financial_deterioration()
    ledger = _monthly_ledger(get_monthly_financial_flow())

    liquid_assets = round(sum(
        _n(item.get("balance_crc"))
        for item in accounts
        if item.get("include_in_net_worth") and item.get("account_type") != "investment"
    ), 2)
    assets_total = round(sum(
        _n(item.get("balance_crc"))
        for item in accounts
        if item.get("include_in_net_worth")
    ), 2)
    debt_total = round(sum(_n(item.get("remaining_amount")) for item in debts), 2)
    monthly_debt = round(sum(_n(item.get("monthly_payment")) for item in debts), 2)

    goal = (strategy.get("summary") or {}).get("main_goal")
    next_action = strategy.get("next_action") or {}
    quality = strategy.get("data_quality") or {}

    return {
        "schema_version": "financial-state-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_id": str(get_current_workspace_id()),
        "period": date.today().strftime("%Y-%m"),
        "cashflow": {
            **ledger,
            "safe_available": round(_n((strategy.get("usable_money") or {}).get("amount")), 2),
            "real_availability": round(_n(availability.get("money_really_available")), 2),
        },
        "balance_sheet": {
            "liquid_assets": liquid_assets,
            "assets_total": assets_total,
            "debt_total": debt_total,
            "net_worth": round(assets_total - debt_total, 2),
        },
        "debt": {
            "active_count": len(debts),
            "total": debt_total,
            "monthly_payments": monthly_debt,
            "target": strategy.get("debt_target"),
        },
        "emergency_fund": {
            "current": round(_n(salvavidas.get("current_amount")), 2),
            "monthly_base": round(_n(salvavidas.get("monthly_base")), 2),
            "coverage_months": round(_n(salvavidas.get("coverage_months")), 2),
            "target_months": int(_n(salvavidas.get("target_months")) or 6),
        },
        "goals": {
            "active": goal,
            "fundable": strategy.get("fundable_goals") or [],
        },
        "health": {
            "score": strategy.get("financial_score"),
            "label": strategy.get("health_label"),
            "confidence": quality.get("confidence"),
            "data_status": quality.get("status"),
            "deterioration": deterioration.get("health"),
        },
        "strategy": {
            "advisor_version": strategy.get("advisor_version"),
            "decision_policy": strategy.get("decision_policy"),
            "next_action": next_action,
            "priorities": strategy.get("priorities") or [],
        },
    }
