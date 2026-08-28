from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth.owner_bridge import require_owner_bridge_key, verify_personal_owner


router = APIRouter(
    prefix="/internal/owner-bridge",
    tags=["Internal Owner Bridge"],
    dependencies=[Depends(require_owner_bridge_key)],
)


class OwnerVerifyRequest(BaseModel):
    personal_supabase_user_id: str


@router.post("/verify")
def verify_owner(payload: OwnerVerifyRequest):
    return verify_personal_owner(payload.personal_supabase_user_id)
