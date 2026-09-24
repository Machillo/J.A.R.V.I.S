from __future__ import annotations

import logging
from typing import Any

from backend.finance.strategic_engine import get_financial_engine_report
from backend.ai.strategy_dashboard import build_local_strategy_blueprint
from backend.advisor.service import get_financial_advice

logger = logging.getLogger(__name__)


def _safe(fn, fallback):
    try:
        return fn()
    except Exception:
        logger.exception("Premium context source failed: %s", getattr(fn, "__name__", "callable"))
        return {"unavailable": True, "fallback": fallback}


def get_current_strategy_summary() -> dict[str, Any]:
    """Show the current financial engine result, never a historical AI guide."""
    blueprint = build_local_strategy_blueprint()
    strategic = _safe(get_financial_engine_report, {})
    advisor = _safe(get_financial_advice, {})
    priority = blueprint.get("priority") or {}
    return {
        "status": "OK",
        "title": blueprint.get("title") or "Estrategia activa",
        "summary": priority.get("detail") or blueprint.get("objective") or "",
        "allocations": blueprint.get("allocation_items") or [],
        "health": strategic.get("health") or {},
        "forecast": strategic.get("forecast") or {},
        "strategy": blueprint,
        "action_plan": advisor.get("action_plan") or [],
        "data_quality": advisor.get("data_quality") or {},
        "decision_policy": advisor.get("decision_policy"),
        "source": "live_database",
    }
