from fastapi import APIRouter

from backend.auth.saas import require_feature
from backend.financial_lifecycle.snapshots import (
    capture_financial_snapshot,
    get_financial_progress,
    list_financial_snapshots,
)
from backend.financial_lifecycle.state import build_financial_state

router = APIRouter(prefix="/user-product/vip/lifecycle", tags=["FINVA Lifecycle"])


@router.get("/state")
def lifecycle_state():
    require_feature("strategy_vip")
    return build_financial_state()


@router.post("/snapshots")
def lifecycle_snapshot():
    require_feature("strategy_vip")
    return capture_financial_snapshot()


@router.get("/snapshots")
def lifecycle_snapshots(limit: int = 90):
    require_feature("strategy_vip")
    return {"status": "OK", "items": list_financial_snapshots(limit)}


@router.get("/progress")
def lifecycle_progress():
    require_feature("strategy_vip")
    return get_financial_progress()
