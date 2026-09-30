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

    result = jarvis_engine.create_initial_financial_strategy()

    assert result["data"]["strategy"] == _blueprint()
    assert result["source"] == "live_database"
    assert "budget" not in result and "guide" not in result


def test_owner_strategy_summary_ignores_old_ai_guides(monkeypatch):
    monkeypatch.setattr(premium_orchestrator, "build_local_strategy_blueprint", _blueprint)
    monkeypatch.setattr(premium_orchestrator, "get_financial_engine_report", lambda: {})
    monkeypatch.setattr(premium_orchestrator, "get_financial_advice", lambda: {})

    result = premium_orchestrator.get_current_strategy_summary()

    assert result["source"] == "live_database"
    assert result["strategy"] == _blueprint()
    assert result["allocations"] == _blueprint()["allocation_items"]


def test_the_owner_strategy_is_no_longer_answered_by_the_chat(monkeypatch):
    # JARVIS Chat's scope (J2) is payroll records and the agenda; the strategy keeps its own
    # endpoint (create_initial_financial_strategy above) and is not built from the chat.
    monkeypatch.setattr(jarvis_engine, "get_pending_action", lambda: None)
    monkeypatch.setattr(jarvis_engine, "build_local_strategy_blueprint",
                        lambda: (_ for _ in ()).throw(AssertionError("the chat must not build the strategy")))

    result = jarvis_engine.process_message("Jarvis, ejecuta mi estrategia premium")

    assert result["status"] == "UNSUPPORTED" and result["pending"] is False
    assert "no está disponible en JARVIS Chat" in result["message"]
