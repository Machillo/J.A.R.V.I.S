from fastapi import APIRouter

from backend.ai.models import JarvisChatRequest, SportsPreferencesRequest, BrowserSubscriptionRequest, MemoryItemRequest, ProfilePreferencesRequest
from backend.ai.jarvis_engine import process_message, create_initial_financial_strategy
from backend.ai.premium_orchestrator import get_current_strategy_summary
from backend.ai.usage_tracker import get_admin_usage_overview, get_today_usage
from backend.ai.openai_client import get_openai_budget_status, get_active_premium_guides
from backend.auth.current_user import get_current_user
from backend.ai.preferences import get_sports_preferences, update_sports_preferences, save_browser_subscription
from backend.core.events import get_upcoming_events
from backend.sports.service import ensure_owner_sports_preferences, get_sports_calendar_summary

from backend.ai.strategy_dashboard import get_premium_strategy_dashboard, get_additional_card_report

from backend.ai.memory_service import (
    create_memory_item,
    forget_memory_item,
    get_profile_preferences,
    list_memory_items,
    memory_summary,
    search_memory_items,
    update_profile_preferences,
)

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


@router.get("/premium/status")
def jarvis_premium_status():
    return get_openai_budget_status()


@router.get("/premium/guides")
def jarvis_premium_guides():
    return {"status": "OK", "items": get_active_premium_guides(limit=10)}


@router.get("/premium/strategy-summary")
def jarvis_premium_strategy_summary():
    return get_current_strategy_summary()


@router.post("/premium/initial-strategy")
def jarvis_premium_initial_strategy():
    return create_initial_financial_strategy()


@router.get("/premium/strategy-dashboard")
def jarvis_premium_strategy_dashboard():
    return get_premium_strategy_dashboard()


@router.get("/cards/additional-report")
def jarvis_additional_cards_report():
    return get_additional_card_report()


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

@router.get("/memory")
def jarvis_memory(category: str | None = None):
    return {"status": "OK", "items": list_memory_items(category=category)}


@router.get("/memory/summary")
def jarvis_memory_summary():
    return memory_summary()


@router.get("/memory/search")
def jarvis_memory_search(q: str = ""):
    return {"status": "OK", "items": search_memory_items(q)}


@router.post("/memory")
def jarvis_create_memory(request: MemoryItemRequest):
    return create_memory_item(
        content=request.content,
        category=request.category,
        title=request.title,
        importance=request.importance,
        source="manual",
    )


@router.delete("/memory/{memory_id}")
def jarvis_delete_memory(memory_id: int):
    return forget_memory_item(memory_id)


@router.get("/preferences/profile")
def jarvis_profile_preferences():
    return {"status": "OK", "value": get_profile_preferences()}


@router.post("/preferences/profile")
def jarvis_update_profile_preferences(request: ProfilePreferencesRequest):
    return update_profile_preferences(request.model_dump(exclude_none=True))

