from backend.financial_lifecycle.monthly_review import build_monthly_review


def _state(*, net_worth, debt, emergency, coverage, score, flow, action):
    return {
        "balance_sheet": {"net_worth": net_worth, "liquid_assets": emergency},
        "debt": {"total": debt},
        "cashflow": {"safe_available": 100, "net_operational": flow},
        "emergency_fund": {"current": emergency, "coverage_months": coverage},
        "health": {"score": score},
        "strategy": {"next_action": action},
    }


def test_monthly_review_returns_baseline_until_two_observations_exist():
    state = _state(
        net_worth=1000, debt=500, emergency=100, coverage=.5, score=50, flow=20,
        action={"type": "emergency_fund", "title": "Completar Salvavidas", "amount": 100},
    )

    review = build_monthly_review(
        period="2026-09",
        closing_state=state,
        observations=[{"snapshot_date": "2026-09-20", "state": state}],
    )

    assert review["status"] == "BASELINE"
    assert review["coverage"]["observations"] == 1
    assert review["next_month"]["priority"] == "emergency_fund"


def test_monthly_review_explains_progress_and_strategy_change():
    baseline = _state(
        net_worth=1000, debt=500, emergency=100, coverage=.5, score=50, flow=20,
        action={"type": "debt", "title": "Abonar deuda", "amount": 100, "why": "Reducir intereses"},
    )
    closing = _state(
        net_worth=1300, debt=350, emergency=200, coverage=1, score=65, flow=80,
        action={"type": "goal", "title": "Financiar meta", "amount": 75, "why": "La deuda cara bajó"},
    )

    review = build_monthly_review(
        period="2026-09",
        closing_state=closing,
        observations=[
            {"snapshot_date": "2026-09-01", "state": baseline},
            {"snapshot_date": "2026-09-30", "state": closing},
        ],
    )

    assert review["status"] == "OK"
    assert review["plan_vs_reality"]["status"] == "met"
    assert review["strategy_evolution"]["kind"] == "priority_changed"
    assert review["finva_value"]["priority_updated"] is True
    assert review["next_month"]["priority"] == "goal"
    assert review["wins"][0]["trend"] == "improved"


def test_monthly_review_surfaces_negative_deviations():
    baseline = _state(
        net_worth=1000, debt=200, emergency=300, coverage=2, score=80, flow=100,
        action={"type": "hold", "title": "Mantener", "amount": 0},
    )
    closing = _state(
        net_worth=800, debt=300, emergency=200, coverage=1, score=60, flow=-50,
        action={"type": "stabilize_cashflow", "title": "Estabilizar", "amount": 50},
    )

    review = build_monthly_review(
        period="2026-09",
        closing_state=closing,
        observations=[
            {"snapshot_date": "2026-09-01", "state": baseline},
            {"snapshot_date": "2026-09-30", "state": closing},
        ],
    )

    assert review["deviations"]
    assert review["headline"] == "Este mes requiere un reajuste financiero."
    assert review["next_month"]["priority"] == "stabilize_cashflow"
