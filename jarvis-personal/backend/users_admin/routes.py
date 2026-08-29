from pydantic import BaseModel
from fastapi import APIRouter, Query

from backend.auth.current_user import require_roles
from backend.users_admin.client import get_user, grant_user_courtesy, link_owner_personal_identity, list_users, revoke_user_courtesy, update_user_access


router = APIRouter(prefix="/users-admin", tags=["JARVIS Users Admin"])


class AccessUpdate(BaseModel):
    plan: str | None = None
    status: str | None = None


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


@router.get("/users/{user_id}")
def user(user_id: int):
    _owner_only()
    return get_user(user_id)


@router.patch("/users/{user_id}/access")
def user_access(user_id: int, payload: AccessUpdate):
    _owner_only()
    return update_user_access(user_id, payload.model_dump(exclude_none=True))


@router.post("/users/{user_id}/courtesy")
def user_courtesy(user_id: int, payload: CourtesyGrant):
    owner = _owner_only()
    return grant_user_courtesy(
        user_id,
        {
            "plan": payload.plan,
            "days": payload.days,
            "note": payload.note,
            "granted_by": owner.get("email") or "owner",
        },
    )


@router.delete("/users/{user_id}/courtesy")
def remove_user_courtesy(user_id: int):
    _owner_only()
    return revoke_user_courtesy(user_id)


@router.post("/owner-link")
def owner_link():
    owner = _owner_only()
    personal_uid = owner.get("supabase_user_id")
    if not personal_uid:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Tu sesión Personal no tiene un Supabase user id vinculado.")
    return link_owner_personal_identity(str(personal_uid))
