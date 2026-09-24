def format_jarvis_response(
    user_message: str,
    intent: str,
    data: dict
):
    # Deterministic wording only: no data leaves DINCR for a generative-AI provider.
    return fallback_response(intent, data)


def fallback_response(intent: str, data: dict):
    if intent in {"highest_debt", "lowest_debt"}:
        debt = data.get("debt")

        if not debt:
            return "Señor, no encontré deudas registradas."

        label = "más alta" if intent == "highest_debt" else "más pequeña"
        return (
            f"Señor, su deuda {label} actualmente es {debt['name']}, "
            f"con un saldo pendiente de ₡{debt['remaining_amount']:,.2f}."
        )

    if intent == "net_worth":
        net_worth = data.get("net_worth")

        return (
            f"Señor, su patrimonio neto actual es de ₡{net_worth:,.2f}."
        )

    if intent == "goal_status":
        goal = data.get("goal")

        if not goal:
            return "Señor, no encontré esa meta registrada."

        return (
            f"Señor, para la meta {goal['name']} le faltan "
            f"₡{goal['remaining_amount']:,.2f}."
        )

    if intent == "user_status":
        return "Señor, ya analicé su estado financiero general."

    if intent == "advisor_summary":
        actions = list(data.get("action_plan") or [])[:3]
        if not actions:
            return "Señor, necesito completar y conciliar sus datos para definir prioridades confiables."
        lines = ["Señor, estas son sus prioridades financieras actuales:"]
        for index, action in enumerate(actions, 1):
            reason = action.get("reason") or action.get("why") or ""
            lines.append(f"{index}. {action.get('title', 'Revisar finanzas')}. {reason}".strip())
        return "\n".join(lines)

    return "Señor, análisis completado."
