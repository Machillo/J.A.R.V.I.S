from fastapi import APIRouter

from backend.ai.models import JarvisChatRequest
from backend.ai.jarvis_engine import process_message
from backend.ai.usage_tracker import get_admin_usage_overview, get_today_usage
from backend.auth.current_user import get_current_user

router = APIRouter(
    prefix="/jarvis",
    tags=["Jarvis AI"]
)


@router.post("/chat")
def jarvis_chat(request: JarvisChatRequest):
    return process_message(request.message)


@router.get("/usage/today")
def jarvis_usage_today():
    return get_today_usage()


@router.get("/usage/admin")
def jarvis_usage_admin():
    user = get_current_user()
    if user.get("role") not in {"owner", "admin"}:
        return {"status": "FORBIDDEN", "message": "Solo admin puede ver consumo global."}
    return get_admin_usage_overview()
