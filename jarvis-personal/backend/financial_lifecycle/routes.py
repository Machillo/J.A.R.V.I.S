from fastapi import APIRouter, HTTPException

from backend.auth.saas import require_feature
from backend.financial_lifecycle.snapshots import (
    capture_financial_snapshot,
    get_financial_progress,
    get_monthly_review,
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


@router.get("/monthly-review")
def lifecycle_monthly_review(period: str | None = None):
    require_feature("strategy_vip")
    try:
        return get_monthly_review(period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
