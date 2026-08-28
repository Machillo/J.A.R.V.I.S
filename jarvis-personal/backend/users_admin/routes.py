from pydantic import BaseModel
from fastapi import APIRouter, Query

from backend.auth.current_user import require_roles
from backend.users_admin.client import get_user, list_users, update_user_access


router = APIRouter(prefix="/users-admin", tags=["JARVIS Users Admin"])


class AccessUpdate(BaseModel):
    plan: str | None = None
    status: str | None = None


def _owner_only():
    return require_roles("owner")


@router.get("/users")
def users(search: str | None = Query(default=None, max_length=120)):
    _owner_only()
    return list_users(search)


@router.get("/users/{user_id}")
def user(user_id: int):
    _owner_only()
    return get_user(user_id)


@router.patch("/users/{user_id}/access")
def user_access(user_id: int, payload: AccessUpdate):
    _owner_only()
    return update_user_access(user_id, payload.model_dump(exclude_none=True))
