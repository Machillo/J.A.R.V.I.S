def interpret(text: str):
    text = text.lower().strip()

    if "hora" in text or "fecha" in text:
        return "GET_TIME"

    if "quién soy" in text or "quien soy" in text:
        return "GET_USER"

    if "config" in text or "configuración" in text or "configuracion" in text:
        return "GET_CONFIG"

    if "evento" in text or "eventos" in text:
        return "GET_EVENTS"

    if "logs" in text or "historial" in text:
        return "GET_LOGS"
    
    if (
        ("cuánto debo" in text or "cuanto debo" in text)
        and ("popular" in text or "bac" in text or "reloj" in text or "minicuotas" in text)
    ):
        return "GET_DEBT_BY_NAME"

    if "cuánto debo" in text or "cuanto debo" in text or "deuda total" in text:
        return "GET_TOTAL_DEBT"

    if (
        "cuánto tengo libre" in text
        or "cuanto tengo libre" in text
        or "dinero libre" in text
        or "disponible" in text
    ):
        return "GET_AVAILABLE_CASH"

    if (
        "cuánto puedo gastar" in text
        or "cuanto puedo gastar" in text
        or "puedo gastar" in text
        or "puedo comprar" in text
        or "me alcanza" in text
    ):
        return "CHECK_SPENDING"

    if (
        "resumen financiero" in text
        or "estado financiero" in text
        or "cómo estoy financieramente" in text
        or "como estoy financieramente" in text
    ):
        return "GET_FINANCIAL_SUMMARY"
    
    if (
        "estrategia" in text
        or "qué hago con mi dinero" in text
        or "que hago con mi dinero" in text
        or "qué recomiendas financieramente" in text
        or "que recomiendas financieramente" in text
    ):
        return "GET_RECOMMENDED_STRATEGY"

    return "UNKNOWN"