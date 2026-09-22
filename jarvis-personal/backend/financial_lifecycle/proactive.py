"""Deterministic, ingestion-agnostic signals for DINCR Proactive Advisor."""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

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
            "message": "DINCR necesita una observación anterior para detectar cambios significativos.",
        }

    comparison = compare_states(current, previous)
    metrics = comparison["metrics"]
    alerts: list[dict[str, Any]] = []

    safe = metrics["safe_available"]
    if _material_drop(safe, absolute=25_000, ratio=.20):
        severity = "critical" if safe["current"] < 0 else "high"
        alerts.append(_alert(
            "safe_available_drop", severity, "Bajó tu dinero seguro disponible",
            f"Cambió {safe['delta']:+,.0f} CRC desde la observación anterior.",
            "Revisar flujo", "finance", safe, baseline_date, today,
        ))

    flow = metrics["net_operational"]
    if _material_drop(flow, absolute=25_000, ratio=.15):
        alerts.append(_alert(
            "cashflow_deterioration", "high" if flow["current"] < 0 else "medium",
            "El flujo operativo se deterioró",
            f"El resultado mensual cambió {flow['delta']:+,.0f} CRC.",
            "Revisar movimientos", "finance", flow, baseline_date, today,
        ))

    debt = metrics["debt_total"]
    if debt["delta"] >= max(25_000, abs(debt["baseline"]) * .05):
        alerts.append(_alert(
            "debt_increase", "high", "La deuda total aumentó",
            f"El saldo creció {debt['delta']:,.0f} CRC desde {baseline_date}.",
            "Revisar deudas", "debts", debt, baseline_date, today,
        ))

    coverage = metrics["emergency_coverage_months"]
    if coverage["delta"] <= -.25:
        alerts.append(_alert(
            "emergency_coverage_drop", "high" if coverage["current"] < 1 else "medium",
            "Disminuyó tu cobertura de emergencia",
            f"La cobertura bajó {abs(coverage['delta']):.2f} meses.",
            "Revisar Salvavidas", "vip-emergency", coverage, baseline_date, today,
        ))

    health = metrics["health_score"]
    if health["delta"] <= -5:
        alerts.append(_alert(
            "health_score_drop", "high" if health["delta"] <= -15 else "medium",
            "Bajó tu salud financiera",
            f"El indicador cambió {health['delta']:+.0f} puntos.",
            "Ver diagnóstico", "situation", health, baseline_date, today,
        ))

    transition = comparison["strategy_transition"]
    if transition["changed"]:
        alerts.append(_alert(
            "strategy_changed", "medium", "DINCR reajustó tu estrategia",
            transition["reason"] or "La prioridad cambió con la nueva información.",
            "Ver nueva estrategia", "strategy", transition, baseline_date, today,
        ))

    debt_reduction = -debt["delta"]
    if debt_reduction >= max(25_000, abs(debt["baseline"]) * .05):
        alerts.append(_alert(
            "debt_progress", "success", "Tu deuda disminuyó",
            f"Redujiste el saldo en {debt_reduction:,.0f} CRC.",
            "Ver progreso", "vip-monthly-review", debt, baseline_date, today,
        ))

    crossed = _coverage_milestone(coverage["baseline"], coverage["current"])
    if crossed:
        alerts.append(_alert(
            f"emergency_milestone_{crossed}", "success", "Alcanzaste un hito de protección",
            f"Tu fondo ya cubre al menos {crossed} {'mes' if crossed == 1 else 'meses'}.",
            "Ver Salvavidas", "vip-emergency", coverage, baseline_date, today,
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
        "message": "DINCR detectó cambios que merecen atención." if alerts else "No hay cambios significativos desde la observación anterior.",
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
