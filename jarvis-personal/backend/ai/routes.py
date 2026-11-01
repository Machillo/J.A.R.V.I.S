from fastapi import APIRouter, Depends

from backend.ai.models import ExactDistributionConfirmRequest, ExactDistributionRequest, JarvisChatRequest, SportsPreferencesRequest, BrowserSubscriptionRequest, ProfilePreferencesRequest
from backend.ai.jarvis_engine import process_message, create_initial_financial_strategy
from backend.ai.owner_distribution import confirm_owner_distribution
from backend.ai.premium_orchestrator import get_current_strategy_summary
from backend.auth.current_user import require_owner
from backend.ai.preferences import get_sports_preferences, update_sports_preferences, save_browser_subscription
from backend.core.events import get_upcoming_events
from backend.sports.service import ensure_owner_sports_preferences, get_sports_calendar_summary

from backend.ai.owner_debt_blocks import get_owner_debt_savings_blocks
from backend.ai.strategy_dashboard import get_additional_card_report, get_owner_exact_distribution, get_premium_strategy_dashboard

from backend.ai.profile_preferences import get_profile_preferences, update_profile_preferences

def require_internal_role():
    # JARVIS is the Owner's: the single verified Owner, never another role.
    return require_owner()


router = APIRouter(
    prefix="/jarvis",
    tags=["Internal AI"],
    dependencies=[Depends(require_internal_role)],
)


@router.post("/chat")
def jarvis_chat(request: JarvisChatRequest):
    return process_message(request.message)


@router.get("/premium/strategy-summary")
def jarvis_premium_strategy_summary():
    return get_current_strategy_summary()


@router.post("/premium/initial-strategy")
def jarvis_premium_initial_strategy():
    """Compatibility endpoint: calculate a live strategy without AI or persistence."""
    return create_initial_financial_strategy()


@router.get("/premium/strategy-dashboard")
def jarvis_premium_strategy_dashboard():
    return get_premium_strategy_dashboard()


@router.get("/premium/debt-savings-blocks")
def jarvis_debt_savings_blocks():
    """The next locked savings block for a debt, by the strategy (read-only proposal)."""
    return get_owner_debt_savings_blocks()


@router.post("/premium/strategy-dashboard/exact-distribution")
def jarvis_exact_distribution(request: ExactDistributionRequest):
    """The current strategy applied to an amount the Owner confirms. A POST so the amount travels in
    the body, never in a URL or log; it writes and stores nothing (a planning answer)."""
    return get_owner_exact_distribution(request.amount, request.currency)


@router.post("/premium/strategy-dashboard/exact-distribution/confirm")
def jarvis_confirm_exact_distribution(request: ExactDistributionConfirmRequest):
    """CONFIRMAR: records the distribution the Owner carried out (debt payments, Salvavidas, goal,
    investment reserve) in one transaction, once per confirmation key."""
    return confirm_owner_distribution(
        request.amount, request.currency, request.confirmation_key,
        [item.model_dump() for item in request.expected_items], request.plan_fingerprint,
    )


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

@router.get("/preferences/profile")
def jarvis_profile_preferences():
    return {"status": "OK", "value": get_profile_preferences()}


@router.post("/preferences/profile")
def jarvis_update_profile_preferences(request: ProfilePreferencesRequest):
    return update_profile_preferences(request.model_dump(exclude_none=True))
