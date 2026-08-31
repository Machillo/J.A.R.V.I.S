from pydantic import BaseModel
from fastapi import APIRouter, Query

from backend.auth.current_user import require_roles
from backend.users_admin.client import get_user, grant_user_courtesy, list_users, revoke_user_courtesy

router = APIRouter(prefix="/users-admin", tags=["Unified User Admin"])

class CourtesyGrant(BaseModel):
    plan: str
    days: int
    note: str | None = None

def _owner_only():
    return require_roles("owner")

@router.get("/users")
def users(search: str | None = Query(default=None, max_length=120)):
    _owner_only()
    return list_users(search)

@router.get("/users/{account_id}")
def user(account_id: str):
    _owner_only()
    return get_user(account_id)

@router.post("/users/{account_id}/courtesy")
def courtesy(account_id: str, payload: CourtesyGrant):
    _owner_only()
    return grant_user_courtesy(account_id, payload.plan, payload.days, payload.note)

@router.delete("/users/{account_id}/courtesy")
def remove_courtesy(account_id: str):
    _owner_only()
    return revoke_user_courtesy(account_id)
