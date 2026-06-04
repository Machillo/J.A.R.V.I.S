from fastapi import APIRouter, Request

from backend.auth.models import AllowedUserRequest, CheckAccessRequest
from backend.auth.service import (
    get_allowed_users,
    create_allowed_user,
    delete_allowed_user,
    check_user_access,
)
from backend.auth.current_user import get_current_user, require_roles


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
    return get_current_user()
