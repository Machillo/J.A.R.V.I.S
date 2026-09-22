from datetime import date

from backend.financial_lifecycle.progress import build_longitudinal_progress, compare_states


def _state(*, net_worth, debt, liquid, emergency, coverage, score, action):
    return {
        "balance_sheet": {"net_worth": net_worth, "liquid_assets": liquid},
        "debt": {"total": debt},
        "cashflow": {"safe_available": 100, "net_operational": 50},
        "emergency_fund": {"current": emergency, "coverage_months": coverage},
        "health": {"score": score},
        "strategy": {"next_action": action},
    }


def test_compare_states_directs_lower_debt_as_improvement():
    prior = _state(
        net_worth=1000, debt=600, liquid=400, emergency=100, coverage=.5, score=50,
        action={"type": "debt", "title": "Pagar deuda", "amount": 100},
    )
    current = _state(
        net_worth=1200, debt=450, liquid=450, emergency=150, coverage=.8, score=60,
        action={"type": "emergency_fund", "title": "Completar Salvavidas", "amount": 80},
    )

    comparison = compare_states(current, prior)

    assert comparison["metrics"]["debt_total"]["delta"] == -150
    assert comparison["metrics"]["debt_total"]["trend"] == "improved"
    assert comparison["strategy_transition"]["changed"] is True
    assert comparison["plan_vs_reality"]["actual_amount"] == 150
    assert comparison["plan_vs_reality"]["status"] == "met"


def test_longitudinal_progress_uses_snapshot_at_or_before_each_cutoff():
    current = _state(
        net_worth=2000, debt=200, liquid=800, emergency=500, coverage=2, score=80,
        action={"type": "goal", "title": "Financiar meta", "amount": 50},
    )
    history = [
        {"snapshot_date": "2026-08-15", "state": _state(net_worth=1500, debt=300, liquid=600, emergency=300, coverage=1, score=70, action={"type": "debt", "amount": 100})},
        {"snapshot_date": "2026-06-01", "state": _state(net_worth=1000, debt=500, liquid=300, emergency=100, coverage=.4, score=45, action={"type": "emergency_fund", "amount": 200})},
    ]

    result = build_longitudinal_progress(current, history, as_of=date(2026, 9, 20))

    assert result["windows"]["30"]["baseline_date"] == "2026-08-15"
    assert result["windows"]["90"]["baseline_date"] == "2026-06-01"
    assert result["windows"]["180"] is None
    assert result["windows"]["365"] is None


def test_unmeasurable_action_is_explicit_instead_of_inventing_progress():
    prior = _state(net_worth=100, debt=0, liquid=100, emergency=50, coverage=1, score=60, action={"type": "goal", "title": "Viaje", "amount": 25})
    current = _state(net_worth=120, debt=0, liquid=120, emergency=50, coverage=1, score=62, action={"type": "goal", "title": "Viaje", "amount": 25})

    result = compare_states(current, prior)["plan_vs_reality"]

    assert result["actual_amount"] is None
    assert result["status"] == "not_measurable"
