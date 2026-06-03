from fastapi import APIRouter

from backend.auth.models import AllowedUserRequest
from backend.auth.service import (
    get_allowed_users,
    create_allowed_user,
    delete_allowed_user
)


router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)


@router.get("/health")
def health():
    return {
        "status": "ok",
        "module": "auth"
    }


@router.get("/allowed-users")
def allowed_users():
    return get_allowed_users()

@router.post("/allowed-users")
def add_allowed_user(request: AllowedUserRequest):
    return create_allowed_user(
        email=request.email,
        role=request.role,
        status=request.status
    )

@router.delete("/allowed-users/{user_id}")
def remove_allowed_user(user_id: int):
    return delete_allowed_user(user_id)