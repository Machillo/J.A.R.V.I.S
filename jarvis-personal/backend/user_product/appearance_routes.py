"""Personal appearance routes (`/user-product/appearance`).

Phase 1 is an Owner-only experiment: every route calls `require_owner()` itself, so Free, Basic
and VIP accounts get 403 from the server whatever a client shows. Opening it to more accounts
later is a deliberate change of this gate (and of the reviewed route inventory, R1); the service
(appearance.py) is already neutral and per account.
"""
from fastapi import APIRouter

from backend.auth.current_user import require_owner
from backend.user_product.appearance import AppearancePreferences, get_appearance, reset_appearance, save_appearance

router = APIRouter(prefix="/user-product", tags=["DINCR Product"])


@router.get("/appearance")
def read_appearance():
    require_owner()
    return get_appearance()


@router.put("/appearance")
def write_appearance(request: AppearancePreferences):
    require_owner()
    return save_appearance(request)


@router.delete("/appearance")
def restore_default_appearance():
    require_owner()
    return reset_appearance()
