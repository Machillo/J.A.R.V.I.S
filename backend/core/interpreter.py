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

    return "UNKNOWN"