from datetime import date

from backend.financial_lifecycle.proactive import build_proactive_advisor


def _state(*, safe=100_000, flow=50_000, debt=500_000, coverage=1.5, health=70, action=None):
    return {
        "balance_sheet": {"net_worth": 1_000_000, "liquid_assets": 200_000},
        "debt": {"total": debt},
        "cashflow": {"safe_available": safe, "net_operational": flow},
        "emergency_fund": {"current": 200_000, "coverage_months": coverage},
        "health": {"score": health},
        "strategy": {"next_action": action or {"type": "debt", "title": "Abonar deuda", "amount": 50_000}},
    }


def test_proactive_advisor_requires_previous_observation():
    result = build_proactive_advisor(
        current=_state(), previous=None, baseline_date=None, as_of=date(2026, 9, 21),
    )

    assert result["status"] == "BASELINE"
    assert result["alerts"] == []


def test_proactive_advisor_ignores_immaterial_changes():
    previous = _state()
    current = _state(safe=90_000, flow=45_000, debt=510_000, coverage=1.4, health=68)

    result = build_proactive_advisor(
        current=current, previous=previous, baseline_date="2026-09-20", as_of=date(2026, 9, 21),
    )

    assert result["status"] == "STABLE"
    assert result["alerts"] == []


def test_proactive_advisor_detects_material_deterioration_and_actions():
    previous = _state()
    current = _state(
        safe=-10_000, flow=-20_000, debt=550_000, coverage=.8, health=52,
        action={"type": "stabilize_cashflow", "title": "Estabilizar flujo", "amount": 20_000},
    )

    result = build_proactive_advisor(
        current=current, previous=previous, baseline_date="2026-09-20", as_of=date(2026, 9, 21),
    )
    by_code = {item["code"]: item for item in result["alerts"]}

    assert result["status"] == "ALERTS"
    assert by_code["safe_available_drop"]["severity"] == "critical"
    assert by_code["debt_increase"]["action"]["route"] == "debts"
    assert by_code["emergency_coverage_drop"]["action"]["route"] == "vip-emergency"
    assert by_code["strategy_changed"]["action"]["route"] == "strategy"
    assert result["summary"]["urgent"] >= 1


def test_proactive_advisor_celebrates_material_debt_progress_and_milestone():
    previous = _state(debt=500_000, coverage=.8)
    current = _state(debt=450_000, coverage=1.1)

    result = build_proactive_advisor(
        current=current, previous=previous, baseline_date="2026-09-20", as_of=date(2026, 9, 21),
    )
    codes = {item["code"] for item in result["alerts"]}

    assert "debt_progress" in codes
    assert "emergency_milestone_1" in codes
    assert result["summary"]["positive"] == 2


def test_signal_ids_are_stable_for_same_dates_and_code():
    kwargs = {
        "current": _state(debt=450_000),
        "previous": _state(debt=500_000),
        "baseline_date": "2026-09-20",
        "as_of": date(2026, 9, 21),
    }

    first = build_proactive_advisor(**kwargs)
    second = build_proactive_advisor(**kwargs)

    assert [item["id"] for item in first["alerts"]] == [item["id"] for item in second["alerts"]]
