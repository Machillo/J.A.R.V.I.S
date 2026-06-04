import json

from backend.ai.gemini_client import ask_gemini


AVAILABLE_INTENTS = [
    "highest_debt",
    "debt_summary",
    "net_worth",
    "user_status",
    "goal_status",
    "spending_habits",
    "advisor_summary",
    "unknown",
]


def detect_intent(user_message: str):
    prompt = f"""
Eres el clasificador de intenciones de JARVIS.

Tu única tarea es convertir el mensaje del usuario en JSON válido.

Intenciones disponibles:
{AVAILABLE_INTENTS}

Reglas:
- Responde SOLO JSON.
- No expliques.
- No uses markdown.
- Si el usuario pregunta por la deuda más grande, mayor deuda o deuda más alta, usa "highest_debt".
- Si pregunta por estado financiero general, usa "user_status".
- Si pregunta por patrimonio, usa "net_worth".
- Si pregunta por hábitos o gastos, usa "spending_habits".
- Si pregunta por recomendación o estrategia, usa "advisor_summary".
- Si pregunta por una meta específica como Ecuador o Japón, usa "goal_status".
- Si no entiendes, usa "unknown".

Formato:
{{
  "intent": "highest_debt",
  "entity": null,
  "confidence": 0.95
}}

Mensaje del usuario:
"{user_message}"
"""

    ai_response = ask_gemini(prompt)

    if ai_response["status"] != "OK":
        return {
            "intent": "unknown",
            "entity": None,
            "confidence": 0,
            "source": "fallback",
            "error": ai_response.get("message"),
        }

    text = ai_response["text"].strip()

    try:
        parsed = json.loads(text)

        return {
            "intent": parsed.get("intent", "unknown"),
            "entity": parsed.get("entity"),
            "confidence": parsed.get("confidence", 0),
            "source": "gemini",
        }

    except json.JSONDecodeError:
        return {
            "intent": "unknown",
            "entity": None,
            "confidence": 0,
            "source": "gemini_parse_error",
            "raw": text,
        }