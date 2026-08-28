from backend.finance.service import get_strategy_basic, get_summary


def chat_basic(message: str) -> dict:
    text = (message or "").strip().lower()
    if not text:
        return {"message": "Escribí una pregunta sobre tus finanzas."}

    if any(word in text for word in ("resumen", "saldo", "disponible", "ingreso", "gasto")):
        summary = get_summary()
        return {
            "message": (
                f"Este mes registrás ₡{summary['income']:,.0f} de ingresos y ₡{summary['expenses']:,.0f} de gastos. "
                f"Después de cuotas de deuda te quedan ₡{summary['available_after_commitments']:,.0f}."
            ),
            "data": summary,
        }

    if any(word in text for word in ("estrategia", "deuda", "prioridad")):
        strategy = get_strategy_basic()
        return {"message": strategy["recommendation"], "data": strategy}

    return {
        "message": "Por ahora puedo ayudarte con tu resumen financiero, gastos, ingresos, deuda y estrategia básica."
    }
