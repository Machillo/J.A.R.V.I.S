from fastapi import APIRouter

from backend.ai.models import ChatRequest
from backend.ai.service import chat_basic


router = APIRouter(prefix="/jarvis", tags=["JARVIS Basic"])


@router.post("/chat")
def chat(request: ChatRequest):
    return chat_basic(request.message)
