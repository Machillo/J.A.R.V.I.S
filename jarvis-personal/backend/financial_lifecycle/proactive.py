"""Deterministic, ingestion-agnostic signals for DINCR Proactive Advisor."""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any
from backend.core.i18n import tx

from backend.financial_lifecycle.progress import compare_states


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_proactive_advisor(
    *,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    baseline_date: str | None,
    as_of: date | None = None,
) -> dict[str, Any]:
    today = as_of or date.today()
    if not previous:
        return {
            "status": "BASELINE",
            "as_of": today.isoformat(),
            "baseline_date": None,
            "alerts": [],
            "summary": {"urgent": 0, "attention": 0, "positive": 0},
            "message": tx("DINCR todavía no tiene una revisión anterior para comparar y detectar cambios importantes.", "DINCR doesn’t have an earlier check to compare with yet, so it can’t detect important changes."),
        }

    comparison = compare_states(current, previous)
    metrics = comparison["metrics"]
    alerts: list[dict[str, Any]] = []

    safe = metrics["safe_available"]
    if _material_drop(safe, absolute=25_000, ratio=.20):
        severity = "critical" if safe["current"] < 0 else "high"
        alerts.append(_alert(
            "safe_available_drop", severity, tx("Bajó el dinero que podés usar con tranquilidad", "The money you can safely use dropped"),
            tx(f"Cambió {safe['delta']:+,.0f} CRC desde la última revisión.", f"It changed {safe['delta']:+,.0f} CRC since the last check."),
            tx("Revisar movimientos", "Review transactions"), "finance", safe, baseline_date, today,
        ))

    flow = metrics["net_operational"]
    if _material_drop(flow, absolute=25_000, ratio=.15):
        alerts.append(_alert(
            "cashflow_deterioration", "high" if flow["current"] < 0 else "medium",
            tx("Te queda menos dinero al final del mes", "You have less money left at the end of the month"),
            tx(f"Tus ingresos menos tus gastos cambiaron {flow['delta']:+,.0f} CRC.", f"Your income minus your expenses changed {flow['delta']:+,.0f} CRC."),
            tx("Revisar movimientos", "Review transactions"), "finance", flow, baseline_date, today,
        ))

    debt = metrics["debt_total"]
    if debt["delta"] >= max(25_000, abs(debt["baseline"]) * .05):
        alerts.append(_alert(
            "debt_increase", "high", tx("La deuda total aumentó", "Total debt increased"),
            tx(f"El saldo creció {debt['delta']:,.0f} CRC desde {baseline_date}.", f"The balance grew {debt['delta']:,.0f} CRC since {baseline_date}."),
            tx("Revisar deudas", "Review debts"), "debts", debt, baseline_date, today,
        ))

    coverage = metrics["emergency_coverage_months"]
    if coverage["delta"] <= -.25:
        alerts.append(_alert(
            "emergency_coverage_drop", "high" if coverage["current"] < 1 else "medium",
            tx("Tu fondo de emergencia cubre menos meses", "Your emergency fund covers fewer months"),
            tx(f"Ahora cubre {abs(coverage['delta']):.2f} meses menos.", f"It now covers {abs(coverage['delta']):.2f} fewer months."),
            tx("Revisar Salvavidas", "Review emergency fund"), "vip-emergency", coverage, baseline_date, today,
        ))

    health = metrics["health_score"]
    if (current.get("health") or {}).get("missing"):
        # The score can't be stated (no comparison is made from it): say why and where to fix it.
        alerts.append(_alert(
            "health_score_incomplete", "medium",
            tx("Falta la tasa de interés de una deuda", "A debt's interest rate is missing"),
            tx("DINCR la necesita para completar tu salud financiera.", "DINCR needs it to complete your financial health."),
            tx("Revisar deudas", "Review debts"), "debts", health, baseline_date, today,
        ))
    elif health["delta"] is not None and health["delta"] <= -5:
        alerts.append(_alert(
            "health_score_drop", "high" if health["delta"] <= -15 else "medium",
            tx("Bajó tu salud financiera", "Your financial health dropped"),
            tx(f"El indicador cambió {health['delta']:+.0f} puntos.", f"The score changed {health['delta']:+.0f} points."),
            tx("Ver diagnóstico", "View diagnosis"), "situation", health, baseline_date, today,
        ))

    transition = comparison["strategy_transition"]
    if transition["changed"]:
        alerts.append(_alert(
            "strategy_changed", "medium", tx("DINCR reajustó tu estrategia", "DINCR readjusted your strategy"),
            transition["reason"] or tx("La prioridad cambió con la nueva información.", "The priority changed with the new information."),
            tx("Ver nueva estrategia", "View new strategy"), "strategy", transition, baseline_date, today,
        ))

    debt_reduction = -debt["delta"]
    if debt_reduction >= max(25_000, abs(debt["baseline"]) * .05):
        alerts.append(_alert(
            "debt_progress", "success", tx("Tu deuda disminuyó", "Your debt decreased"),
            tx(f"Redujiste el saldo en {debt_reduction:,.0f} CRC.", f"You reduced the balance by {debt_reduction:,.0f} CRC."),
            tx("Ver progreso", "View progress"), "vip-monthly-review", debt, baseline_date, today,
        ))

    crossed = _coverage_milestone(coverage["baseline"], coverage["current"])
    if crossed:
        alerts.append(_alert(
            f"emergency_milestone_{crossed}", "success", tx("Alcanzaste un hito de protección", "You reached a protection milestone"),
            tx(f"Tu fondo ya cubre al menos {crossed} {'mes' if crossed == 1 else 'meses'}.", f"Your fund now covers at least {crossed} {'month' if crossed == 1 else 'months'}."),
            tx("Ver Salvavidas", "View emergency fund"), "vip-emergency", coverage, baseline_date, today,
        ))

    order = {"critical": 0, "high": 1, "medium": 2, "success": 3}
    alerts.sort(key=lambda item: (order[item["severity"]], item["code"]))
    return {
        "status": "ALERTS" if alerts else "STABLE",
        "as_of": today.isoformat(),
        "baseline_date": baseline_date,
        "alerts": alerts,
        "summary": {
            "urgent": sum(item["severity"] in {"critical", "high"} for item in alerts),
            "attention": sum(item["severity"] == "medium" for item in alerts),
            "positive": sum(item["severity"] == "success" for item in alerts),
        },
        "message": tx("DINCR detectó cambios que merecen atención.", "DINCR detected changes worth your attention.") if alerts else tx("No hay cambios importantes desde la última revisión.", "No important changes since the last check."),
    }


def _material_drop(metric: dict[str, Any], *, absolute: float, ratio: float) -> bool:
    drop = -_n(metric.get("delta"))
    baseline = abs(_n(metric.get("baseline")))
    return drop >= absolute and (baseline == 0 or drop >= baseline * ratio)


def _coverage_milestone(before: float, after: float) -> int | None:
    return next((milestone for milestone in (6, 3, 1) if before < milestone <= after), None)


def _alert(
    code: str,
    severity: str,
    title: str,
    explanation: str,
    action_label: str,
    action_route: str,
    evidence: dict[str, Any],
    baseline_date: str | None,
    today: date,
) -> dict[str, Any]:
    raw_key = f"{code}:{baseline_date}:{today.isoformat()}"
    return {
        "id": hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16],
        "code": code,
        "severity": severity,
        "title": title,
        "explanation": explanation,
        "action": {"label": action_label, "route": action_route},
        "evidence": evidence,
    }
