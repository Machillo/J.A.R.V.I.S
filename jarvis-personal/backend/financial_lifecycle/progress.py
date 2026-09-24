"""Pure Phase 2B comparisons over canonical financial-state snapshots."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from backend.core.i18n import tx


WINDOW_DAYS = (30, 90, 180, 365)


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _path(state: dict[str, Any], *parts: str) -> Any:
    value: Any = state
    for part in parts:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


METRICS = (
    ("net_worth", ("balance_sheet", "net_worth"), 1),
    ("debt_total", ("debt", "total"), -1),
    ("liquid_assets", ("balance_sheet", "liquid_assets"), 1),
    ("safe_available", ("cashflow", "safe_available"), 1),
    ("net_operational", ("cashflow", "net_operational"), 1),
    ("emergency_fund_current", ("emergency_fund", "current"), 1),
    ("emergency_coverage_months", ("emergency_fund", "coverage_months"), 1),
    ("health_score", ("health", "score"), 1),
)


def compare_states(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Compare two versioned states without depending on their source or ingestion path."""
    metrics = {}
    for name, path, positive_direction in METRICS:
        current_value = _n(_path(current, *path))
        baseline_value = _n(_path(baseline, *path))
        delta = round(current_value - baseline_value, 2)
        directed = delta * positive_direction
        metrics[name] = {
            "current": round(current_value, 2),
            "baseline": round(baseline_value, 2),
            "delta": delta,
            "trend": "improved" if directed > 0 else "declined" if directed < 0 else "unchanged",
        }

    current_action = _path(current, "strategy", "next_action") or {}
    baseline_action = _path(baseline, "strategy", "next_action") or {}
    current_type = current_action.get("type")
    baseline_type = baseline_action.get("type")
    changed = current_action != baseline_action
    return {
        "metrics": metrics,
        "summary": {
            "improved": sum(item["trend"] == "improved" for item in metrics.values()),
            "declined": sum(item["trend"] == "declined" for item in metrics.values()),
            "unchanged": sum(item["trend"] == "unchanged" for item in metrics.values()),
        },
        "strategy_transition": {
            "changed": changed,
            "kind": "priority_changed" if current_type != baseline_type else "plan_adjusted" if changed else "unchanged",
            "from": baseline_action or None,
            "to": current_action or None,
            "reason": _transition_reason(metrics) if changed else None,
        },
        "plan_vs_reality": _plan_vs_reality(baseline_action, metrics),
    }


def build_longitudinal_progress(
    current: dict[str, Any],
    snapshots: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    today = as_of or date.today()
    normalized = sorted(snapshots, key=lambda item: str(item.get("snapshot_date") or ""), reverse=True)
    windows = {}
    for days in WINDOW_DAYS:
        cutoff = today - timedelta(days=days)
        baseline = next((item for item in normalized if _as_date(item.get("snapshot_date")) <= cutoff), None)
        windows[str(days)] = None if not baseline else {
            "days": days,
            "baseline_date": str(baseline.get("snapshot_date")),
            **compare_states(current, baseline.get("state") or {}),
        }
    return {"as_of": today.isoformat(), "windows": windows}


def _plan_vs_reality(planned_action: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any] | None:
    if not planned_action:
        return None
    action_type = planned_action.get("type")
    planned = max(_n(planned_action.get("amount")), 0)
    if action_type == "debt":
        actual = max(-metrics["debt_total"]["delta"], 0)
    elif action_type == "emergency_fund":
        actual = max(metrics["emergency_fund_current"]["delta"], 0)
    elif action_type in {"stabilize_cashflow", "mitigate_deterioration"}:
        actual = max(metrics["net_operational"]["delta"], 0)
    else:
        actual = None
    variance = round(actual - planned, 2) if actual is not None else None
    return {
        "action_type": action_type,
        "title": planned_action.get("title"),
        "planned_amount": round(planned, 2),
        "actual_amount": round(actual, 2) if actual is not None else None,
        "variance": variance,
        "status": "met" if actual is not None and actual >= planned else "behind" if actual is not None else "not_measurable",
    }


def _transition_reason(metrics: dict[str, Any]) -> str:
    changed = [(name, item) for name, item in metrics.items() if item["delta"]]
    if not changed:
        return tx("La prioridad cambió por nueva información cualitativa o reglas de estrategia.", "The priority changed due to new qualitative information or strategy rules.")
    name, item = max(changed, key=lambda pair: abs(pair[1]["delta"]))
    labels = {
        "net_worth": ("patrimonio neto", "net worth"),
        "debt_total": ("deuda total", "total debt"),
        "liquid_assets": ("activos líquidos", "liquid assets"),
        "safe_available": ("dinero seguro disponible", "safe available money"),
        "net_operational": ("flujo operativo", "operating cash flow"),
        "emergency_fund_current": ("fondo de emergencia", "emergency fund"),
        "emergency_coverage_months": ("cobertura de emergencia", "emergency coverage"),
        "health_score": ("salud financiera", "financial health"),
    }
    label = tx(*labels[name])
    return tx(f"El cambio principal observado fue en {label} ({item['delta']:+.2f}).", f"The main change observed was in {label} ({item['delta']:+.2f}).")


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
