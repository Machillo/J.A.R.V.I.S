import json

from backend.ai.gemini_client import ask_gemini


def format_jarvis_response(
    user_message: str,
    intent: str,
    data: dict
):
    prompt = f"""
Eres JARVIS, un asistente personal privado.

Tu tarea es convertir datos técnicos en una respuesta humana, clara y elegante.

Estilo:
- Habla en español.
- Dirígete al usuario como "Señor".
- Sé breve.
- No muestres JSON.
- No inventes datos.
- No des consejos financieros extremos.
- Si falta información, dilo con claridad.
- Tono: asistente tipo JARVIS / Tony Stark, serio pero cercano.

Mensaje original del usuario:
{user_message}

Intención detectada:
{intent}

Datos reales del sistema:
{json.dumps(data, ensure_ascii=False, indent=2)}

Responde solamente el texto final que verá el usuario.
"""

    ai_response = ask_gemini(prompt)

    if ai_response["status"] != "OK":
        return fallback_response(intent, data)

    return ai_response["text"].strip()


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
        return "Señor, ya preparé una recomendación financiera con los datos actuales."

    return "Señor, análisis completado."