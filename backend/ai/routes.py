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

