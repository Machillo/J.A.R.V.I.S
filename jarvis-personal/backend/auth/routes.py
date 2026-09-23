from fastapi import APIRouter, BackgroundTasks, Request
from backend.product_ops.posthog_events import capture_backend_event

from backend.auth.models import AllowedUserRequest, CheckAccessRequest, LegalAcceptanceRequest, PlanSelectionRequest, ProfileSetupRequest, UnifiedOnboardingRequest
from backend.auth.legal import accept_legal_documents
from backend.auth.data_export import export_current_account_data
from backend.auth.service import (
    get_allowed_users,
    create_allowed_user,
    delete_allowed_user,
    delete_current_account,
    check_user_access,
)
from backend.auth.current_user import get_current_user, require_roles
from backend.auth.saas import complete_onboarding, complete_profile_setup, enrich_identity, get_available_plans, get_onboarding_status, select_plan


router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


@router.get("/health")
def health():
    return {
        "status": "ok",
        "module": "auth",
    }


@router.get("/allowed-users")
def allowed_users():
    require_roles("owner", "admin")
    return get_allowed_users()


@router.post("/allowed-users")
def add_allowed_user(request: AllowedUserRequest):
    require_roles("owner", "admin")
    return create_allowed_user(
        email=request.email,
        role=request.role,
        status=request.status,
    )


@router.delete("/allowed-users/{user_id}")
def remove_allowed_user(user_id: int):
    require_roles("owner", "admin")
    return delete_allowed_user(user_id)


@router.post("/check-access")
def check_access(request: CheckAccessRequest):
    return check_user_access(request.email)


@router.get("/me")
def me():
    return enrich_identity(get_current_user())


@router.get("/me/export")
def export_my_data():
    return export_current_account_data()


@router.delete("/me")
def remove_my_account(background_tasks: BackgroundTasks):
    result = delete_current_account()
    background_tasks.add_task(capture_backend_event, "account_deletion_completed")
    return result


@router.post("/legal/accept")
def accept_legal(request_body: LegalAcceptanceRequest, request: Request):
    return accept_legal_documents(request_body, request)


@router.get("/plans")
def plans():
    return get_available_plans()


@router.post("/profile-setup")
def profile_setup(request: ProfileSetupRequest):
    return complete_profile_setup(request)


@router.post("/plan")
def choose_plan(request: PlanSelectionRequest):
    return select_plan(request.plan, request.accept_beta_terms, request.consent_version)


@router.get("/onboarding")
def onboarding_status():
    return get_onboarding_status()


@router.post("/onboarding")
def onboarding_complete(request: UnifiedOnboardingRequest):
    return complete_onboarding(request)
