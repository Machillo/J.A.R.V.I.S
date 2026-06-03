import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


def is_ai_available():
    return bool(GEMINI_API_KEY) and AI_ENABLED


def ask_gemini(prompt: str):
    if not is_ai_available():
        return {
            "status": "ERROR",
            "message": "IA no disponible."
        }

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        return {
            "status": "OK",
            "text": response.text
        }

    except Exception as error:
        return {
            "status": "ERROR",
            "message": str(error)
        }