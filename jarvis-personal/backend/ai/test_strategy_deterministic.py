from backend.ai import jarvis_engine, premium_orchestrator


def _blueprint():
    return {
        "title": "Estrategia actual",
        "objective": "Cubrir obligaciones",
        "monthly_income": 1000,
        "recurring_monthly_income": 1000,
        "total_debt": 0,
        "allocation": {"fondo_de_emergencia": 100},
        "allocation_amounts": {"fondo_de_emergencia": 300},
        "allocation_items": [{"key": "fondo_de_emergencia", "percentage": 100, "amount": 300}],
    }


def test_owner_initial_strategy_uses_live_engine_without_ai_or_saved_guides(monkeypatch):
    monkeypatch.setattr(jarvis_engine, "build_local_strategy_blueprint", _blueprint)
    monkeypatch.setattr(jarvis_engine, "ask_openai", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("AI must not create strategies")))
    monkeypatch.setattr(jarvis_engine, "get_active_premium_guides", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("Old guides must not determine strategies")))

    result = jarvis_engine.create_initial_financial_strategy()

    assert result["data"]["strategy"] == _blueprint()
    assert result["source"] == "live_database"
    assert "budget" not in result and "guide" not in result


def test_owner_strategy_summary_ignores_old_ai_guides(monkeypatch):
    monkeypatch.setattr(premium_orchestrator, "build_local_strategy_blueprint", _blueprint)
    monkeypatch.setattr(premium_orchestrator, "get_active_premium_guides", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("Old guides must not determine strategies")))
    monkeypatch.setattr(premium_orchestrator, "get_financial_engine_report", lambda: {})
    monkeypatch.setattr(premium_orchestrator, "get_financial_advice", lambda: {})

    result = premium_orchestrator.get_current_strategy_summary()

    assert result["source"] == "live_database"
    assert result["strategy"] == _blueprint()
    assert result["allocations"] == _blueprint()["allocation_items"]


def test_owner_strategy_chat_skips_premium_ai_router(monkeypatch):
    monkeypatch.setattr(jarvis_engine, "get_pending_action", lambda: None)
    monkeypatch.setattr(jarvis_engine, "handle_personal_decision_request", lambda _message: None)
    monkeypatch.setattr(jarvis_engine, "detect_intent", lambda _message: (_ for _ in ()).throw(AssertionError("AI intent detection is not needed for strategy")))
    monkeypatch.setattr(jarvis_engine, "premium_route_command", lambda *_args: (_ for _ in ()).throw(AssertionError("AI must not route strategy requests")))
    monkeypatch.setattr(jarvis_engine, "build_local_strategy_blueprint", _blueprint)

    result = jarvis_engine.process_message("Jarvis, ejecuta mi estrategia premium")

    assert result["intent"] == "financial_strategy"
    assert result["source"] == "live_database"
    assert result["data"]["strategy"]["title"] == "Estrategia actual"
