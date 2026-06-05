from fastapi import APIRouter

from backend.ai.models import JarvisChatRequest, SportsPreferencesRequest, BrowserSubscriptionRequest
from backend.ai.jarvis_engine import process_message
from backend.ai.usage_tracker import get_admin_usage_overview, get_today_usage
from backend.auth.current_user import get_current_user
from backend.ai.preferences import get_sports_preferences, update_sports_preferences, save_browser_subscription
from backend.core.events import get_upcoming_events
from backend.sports.service import ensure_owner_sports_preferences, get_sports_calendar_summary

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


@router.get("/preferences/sports")
def jarvis_sports_preferences():
    return get_sports_preferences()


@router.post("/preferences/sports")
def jarvis_update_sports_preferences(request: SportsPreferencesRequest):
    return update_sports_preferences(request.model_dump(exclude_none=True))


@router.post("/notifications/browser")
def jarvis_browser_notifications(request: BrowserSubscriptionRequest):
    return save_browser_subscription(request.model_dump(exclude_none=True))


@router.get("/calendar/upcoming")
def jarvis_upcoming_calendar(days: int = 30):
    return {"events": get_upcoming_events(days)}


@router.post("/sports/defaults")
def jarvis_set_owner_sports_defaults():
    return ensure_owner_sports_preferences()


@router.get("/sports/radar")
def jarvis_sports_radar(scope: str = "all"):
    return get_sports_calendar_summary(scope)
