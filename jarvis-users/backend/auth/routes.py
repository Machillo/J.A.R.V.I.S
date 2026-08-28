from fastapi import APIRouter

from backend.auth.current_user import get_current_user
from backend.auth.models import FinancialSituationUpdateRequest, OnboardingRequest, PlanSelectionRequest
from backend.auth.onboarding import complete_onboarding, get_onboarding_status
from backend.auth.financial_situation import get_financial_situation, update_financial_situation
from backend.auth.plans import get_available_plans, select_plan


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/health")
def health():
    return {"status": "ok", "module": "auth"}


@router.get("/me")
def me():
    return get_current_user()


@router.get("/plans")
def plans():
    return get_available_plans()


@router.post("/plan")
def choose_plan(request: PlanSelectionRequest):
    return select_plan(request.plan)


@router.get("/onboarding")
def onboarding_status():
    return get_onboarding_status()


@router.post("/onboarding")
def onboarding_complete(request: OnboardingRequest):
    return complete_onboarding(request)


@router.get("/financial-situation")
def financial_situation():
    return get_financial_situation()


@router.put("/financial-situation")
def financial_situation_update(request: FinancialSituationUpdateRequest):
    return update_financial_situation(request)
