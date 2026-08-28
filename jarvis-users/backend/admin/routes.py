from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query

from backend.admin.security import require_admin_api_key
from backend.admin.service import get_user, link_owner_personal_identity, list_users, update_user_access


router = APIRouter(prefix="/admin", tags=["Admin Bridge"], dependencies=[Depends(require_admin_api_key)])


class AccessUpdate(BaseModel):
    plan: str | None = None
    status: str | None = None


class OwnerPersonalLinkRequest(BaseModel):
    personal_supabase_user_id: str


@router.get("/health")
def health():
    return {"status": "ok", "service": "jarvis-users-admin"}


@router.get("/users")
def users(search: str | None = Query(default=None, max_length=120)):
    return list_users(search)


@router.get("/users/{user_id}")
def user(user_id: int):
    return get_user(user_id)


@router.patch("/users/{user_id}/access")
def user_access(user_id: int, payload: AccessUpdate):
    return update_user_access(user_id, plan=payload.plan, status=payload.status)


@router.post("/owner-link")
def owner_link(payload: OwnerPersonalLinkRequest):
    return link_owner_personal_identity(payload.personal_supabase_user_id)
