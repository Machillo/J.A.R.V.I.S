from fastapi import APIRouter

from backend.auth.models import ProfileRoleRequest, ProfileStatusRequest
from backend.auth.service import get_profiles, set_profile_role, set_profile_status
from backend.auth.current_user import get_current_user, require_roles


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/health")
def health():
    return {"status": "ok", "module": "auth"}


@router.get("/profiles")
def profiles():
    require_roles("owner", "admin")
    return get_profiles()


@router.patch("/profiles/{user_id}/role")
def change_profile_role(user_id: int, request: ProfileRoleRequest):
    require_roles("owner")
    return set_profile_role(user_id, request.role)


@router.patch("/profiles/{user_id}/status")
def change_profile_status(user_id: int, request: ProfileStatusRequest):
    require_roles("owner", "admin")
    return set_profile_status(user_id, request.status)


@router.get("/me")
def me():
    return get_current_user()
