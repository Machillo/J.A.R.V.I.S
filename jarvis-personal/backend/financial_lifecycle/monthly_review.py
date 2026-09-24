"""DINCR Phase 2C monthly review built from canonical financial states."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from backend.core.i18n import current_language, tx, voice

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
            "headline": tx("DINCR ya guardó la base para medir tu evolución.", "DINCR saved the baseline to measure your progress."),
            "summary": tx("El próximo cierre podrá comparar lo planeado con lo que realmente ocurrió.", "The next close will compare what was planned with what actually happened."),
            "scorecard": [],
            "wins": [],
            "deviations": [],
            "plan_vs_reality": None,
            "strategy_evolution": None,
            "finva_value": {
                "observations_analyzed": len(ordered),
                "changes_detected": 0,
                "priority_updated": False,
                "explanation": tx("DINCR creó tu punto de partida financiero verificable.", "DINCR created your verifiable financial starting point."),
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
        "plan_vs_reality": _localized_plan(comparison["plan_vs_reality"]),
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
        ("net_worth", tx("Patrimonio neto", "Net worth"), "CRC"),
        ("debt_total", tx("Deuda total", "Total debt"), "CRC"),
        ("emergency_fund_current", tx("Fondo de emergencia", "Emergency fund"), "CRC"),
        ("emergency_coverage_months", tx("Cobertura de emergencia", "Emergency coverage"), "months"),
        ("health_score", tx("Salud financiera", "Financial health"), "points"),
        ("net_operational", tx("Flujo operativo", "Operating cash flow"), "CRC"),
    )
    return [
        {"key": key, "label": label, "unit": unit, **metrics[key]}
        for key, label, unit in definitions
    ]


def _headline(wins: list[dict[str, Any]], deviations: list[dict[str, Any]]) -> str:
    if wins and not deviations:
        return tx("Tu situación financiera avanzó este mes.", "Your financial situation improved this month.")
    if deviations and not wins:
        return tx("Este mes requiere un reajuste financiero.", "This month needs a financial readjustment.")
    if wins and deviations:
        return tx("Hubo progreso, con áreas que DINCR debe reajustar.", "There was progress, with areas DINCR needs to readjust.")
    return tx("Tu situación se mantuvo estable durante el período.", "Your situation stayed stable during the period.")


def _summary(summary: dict[str, int], transition: dict[str, Any]) -> str:
    improved, declined = summary["improved"], summary["declined"]
    movement = tx(
        f"{improved} {'indicador mejoró' if improved == 1 else 'indicadores mejoraron'} y {declined} {'se desvió' if declined == 1 else 'se desviaron'}.",
        f"{improved} {'indicator' if improved == 1 else 'indicators'} improved and {declined} deviated.",
    )
    if transition["kind"] == "priority_changed":
        return f"{movement} " + tx("DINCR cambió la prioridad para responder a la nueva situación.", "DINCR changed the priority to respond to the new situation.")
    if transition["kind"] == "plan_adjusted":
        return f"{movement} " + tx("DINCR mantuvo el objetivo y ajustó la ejecución.", "DINCR kept the goal and adjusted the execution.")
    return f"{movement} " + tx("La prioridad estratégica se mantiene.", "The strategic priority stays the same.")


def _value_explanation(changed: int, transition: dict[str, Any]) -> str:
    noun = tx("cambio relevante" if changed == 1 else "cambios relevantes", "relevant change" if changed == 1 else "relevant changes")
    if transition["changed"]:
        return tx(f"DINCR detectó {changed} {noun} y reajustó la estrategia con evidencia del período.",
                  f"DINCR detected {changed} {noun} and readjusted the strategy with evidence from the period.")
    return tx(f"DINCR verificó {changed} {noun} y confirmó que la prioridad actual sigue siendo válida.",
              f"DINCR verified {changed} {noun} and confirmed the current priority is still valid.")


def _next_month(action: dict[str, Any]) -> dict[str, Any]:
    title, rationale = localized_action(action)
    return {
        "priority": action.get("type") or "observe",
        "title": title or tx("Seguir acumulando historia financiera", "Keep building financial history"),
        "amount": round(float(action.get("amount") or 0), 2),
        "rationale": rationale or tx("DINCR actualizará la recomendación con la próxima observación.", "DINCR will update the recommendation with the next observation."),
    }


def _localized_plan(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan:
        return plan
    title, _ = localized_action({"type": plan.get("action_type"), "title": plan.get("title")})
    return {**plan, "title": title}


# Stored strategy actions are canonical Spanish (see state.build_financial_state).
# English responses rebuild the words from the action type, keeping the same
# names, dates and amounts; the decision itself never changes.
_ENGLISH_ACTIONS = {
    "complete_data": ("Complete your missing financial data", "Without this data DINCR can’t authorize using money."),
    "stabilize_cashflow": ("Avoid a negative balance", "Your projected balance turns negative; cover it first."),
    "mitigate_deterioration": ("Address the detected financial deterioration", "DINCR detected a negative change that needs attention first."),
    "reconcile": ("Complete financial reconciliation", "Real balances must be confirmed before moving surplus."),
    "emergency_fund": ("Complete one month of emergency fund", "It’s the protected minimum before accelerating debt or investing."),
    "debt": ("Pay extra toward your priority debt", "It’s the priority debt in your current strategy."),
    "goal": ("Fund your priority goal", "It’s the active goal with the highest priority and nearest date."),
    "investment": ("Invest the authorized surplus", "There are no remaining financial blockers."),
    "hold": ("Don’t move additional money today", "There is no safe surplus after obligations and protection."),
}
_NAMED_TITLES = {
    "debt": ("Abonar a ", "Pay extra toward "),
    "goal": ("Financiar ", "Fund "),
    "stabilize_cashflow": ("Evitar saldo negativo antes de ", "Avoid a negative balance before "),
}


# The stored rationale comes from the Owner advisor and can carry its personal
# assistant voice; DINCR users get the neutral rationale of the action type.
_SPANISH_RATIONALE = {
    "complete_data": "Sin este dato DINCR no puede autorizar el uso de dinero.",
    "stabilize_cashflow": "Tu saldo proyectado queda negativo; cubrilo primero.",
    "mitigate_deterioration": "DINCR detectó un cambio negativo que requiere atención primero.",
    "reconcile": "Los saldos reales deben confirmarse antes de mover excedentes.",
    "emergency_fund": "Es el mínimo protegido antes de acelerar deuda o invertir.",
    "debt": "Es la deuda prioritaria de tu estrategia actual.",
    "goal": "Es la meta activa de mayor prioridad y fecha.",
    "investment": "No quedan bloqueos financieros previos.",
    "hold": "No existe excedente seguro después de obligaciones y protección.",
}


def localized_action(action: dict[str, Any]) -> tuple[str | None, str | None]:
    """(title, rationale) of a stored strategy action in the response language."""
    title, why = action.get("title"), action.get("why")
    if not action:
        return title, why
    if current_language() == "es":
        return title, voice(why, _SPANISH_RATIONALE.get(action.get("type"), why), why)
    kind = action.get("type")
    english_title, english_why = _ENGLISH_ACTIONS.get(kind, (None, None))
    prefix = _NAMED_TITLES.get(kind)
    if prefix and isinstance(title, str) and title.startswith(prefix[0]) and title[len(prefix[0]):].strip():
        english_title = prefix[1] + title[len(prefix[0]):]
    return english_title, english_why
