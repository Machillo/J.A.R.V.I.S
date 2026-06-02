from fastapi import APIRouter

from backend.decision_engine.models import ExtraMoneyDecisionRequest
from backend.decision_engine.service import decide_extra_money


router = APIRouter(prefix="/decisions", tags=["Decision Engine"])


@router.post("/extra-money")
def extra_money_decision(request: ExtraMoneyDecisionRequest):
    return decide_extra_money(
        amount=request.amount,
        source=request.source,
        description=request.description,
    )