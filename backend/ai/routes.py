from fastapi import APIRouter

from backend.ai.models import JarvisChatRequest
from backend.ai.jarvis_engine import process_message

router = APIRouter(
    prefix="/jarvis",
    tags=["Jarvis AI"]
)


@router.post("/chat")
def jarvis_chat(request: JarvisChatRequest):
    return process_message(request.message)

@router.post("/test-intent")
def test_intent(request: JarvisChatRequest):
    from backend.ai.intent_router import detect_intent

    result = detect_intent(request.message)

    return {
        "message_received": request.message,
        "intent_result": result
    }