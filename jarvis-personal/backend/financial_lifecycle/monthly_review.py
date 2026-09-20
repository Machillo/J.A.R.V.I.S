"""FINVA Phase 2C monthly review built from canonical financial states."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from backend.financial_lifecycle.progress import compare_states


def build_monthly_review(
    *,
    period: str,
    closing_state: dict[str, Any],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Explain the month's evolution without depending on how data was ingested."""
    ordered = sorted(observations, key=lambda item: str(item.get("snapshot_date") or ""))
    baseline_row = ordered[0] if len(ordered) >= 2 else None
    baseline = (baseline_row or {}).get("state") or {}
    closing_date = str((ordered[-1] if ordered else {}).get("snapshot_date") or date.today())
    coverage = {
        "observations": len(ordered),
        "baseline_date": str(baseline_row.get("snapshot_date")) if baseline_row else None,
        "closing_date": closing_date,
        "sufficient": baseline_row is not None,
    }

    if not baseline_row:
        action = ((closing_state.get("strategy") or {}).get("next_action") or {})
        return {
            "status": "BASELINE",
            "review_version": "monthly-review-v1",
            "period": period,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "coverage": coverage,
            "headline": "FINVA ya guardó la base para medir tu evolución.",
            "summary": "El próximo cierre podrá comparar lo planeado con lo que realmente ocurrió.",
            "scorecard": [],
            "wins": [],
            "deviations": [],
            "plan_vs_reality": None,
            "strategy_evolution": None,
            "finva_value": {
                "observations_analyzed": len(ordered),
                "changes_detected": 0,
                "priority_updated": False,
                "explanation": "FINVA creó tu punto de partida financiero verificable.",
            },
            "next_month": _next_month(action),
        }

    comparison = compare_states(closing_state, baseline)
    scorecard = _scorecard(comparison["metrics"])
    wins = [item for item in scorecard if item["trend"] == "improved"][:3]
    deviations = [item for item in scorecard if item["trend"] == "declined"][:3]
    transition = comparison["strategy_transition"]
    action = transition.get("to") or ((closing_state.get("strategy") or {}).get("next_action") or {})
    changed = comparison["summary"]["improved"] + comparison["summary"]["declined"]
    return {
        "status": "OK",
        "review_version": "monthly-review-v1",
        "period": period,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": coverage,
        "headline": _headline(wins, deviations),
        "summary": _summary(comparison["summary"], transition),
        "scorecard": scorecard,
        "wins": wins,
        "deviations": deviations,
        "plan_vs_reality": comparison["plan_vs_reality"],
        "strategy_evolution": transition,
        "finva_value": {
            "observations_analyzed": len(ordered),
            "changes_detected": changed,
            "priority_updated": transition["changed"],
            "explanation": _value_explanation(changed, transition),
        },
        "next_month": _next_month(action),
    }


def _scorecard(metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = (
        ("net_worth", "Patrimonio neto", "CRC"),
        ("debt_total", "Deuda total", "CRC"),
        ("emergency_fund_current", "Fondo de emergencia", "CRC"),
        ("emergency_coverage_months", "Cobertura de emergencia", "months"),
        ("health_score", "Salud financiera", "points"),
        ("net_operational", "Flujo operativo", "CRC"),
    )
    return [
        {"key": key, "label": label, "unit": unit, **metrics[key]}
        for key, label, unit in definitions
    ]


def _headline(wins: list[dict[str, Any]], deviations: list[dict[str, Any]]) -> str:
    if wins and not deviations:
        return "Tu situación financiera avanzó este mes."
    if deviations and not wins:
        return "Este mes requiere un reajuste financiero."
    if wins and deviations:
        return "Hubo progreso, con áreas que FINVA debe reajustar."
    return "Tu situación se mantuvo estable durante el período."


def _summary(summary: dict[str, int], transition: dict[str, Any]) -> str:
    movement = f"{summary['improved']} indicadores mejoraron y {summary['declined']} se desviaron."
    if transition["kind"] == "priority_changed":
        return f"{movement} FINVA cambió la prioridad para responder a la nueva situación."
    if transition["kind"] == "plan_adjusted":
        return f"{movement} FINVA mantuvo el objetivo y ajustó la ejecución."
    return f"{movement} La prioridad estratégica se mantiene."


def _value_explanation(changed: int, transition: dict[str, Any]) -> str:
    if transition["changed"]:
        return f"FINVA detectó {changed} cambios relevantes y reajustó la estrategia con evidencia del período."
    return f"FINVA verificó {changed} cambios relevantes y confirmó que la prioridad actual sigue siendo válida."


def _next_month(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "priority": action.get("type") or "observe",
        "title": action.get("title") or "Seguir acumulando historia financiera",
        "amount": round(float(action.get("amount") or 0), 2),
        "rationale": action.get("why") or "FINVA actualizará la recomendación con la próxima observación.",
    }
