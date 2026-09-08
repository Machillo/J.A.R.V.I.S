from fastapi import APIRouter
from backend.advisor.service import (
    get_financial_advice,
    analyze_spending_habits,
)
from backend.advisor.core import get_strategy_history

router = APIRouter(prefix="/advisor", tags=["Advisor"])


@router.get("/summary")
def advisor_summary():
    return get_financial_advice()


@router.get("/strategy")
def advisor_strategy():
    return get_financial_advice()


@router.get("/habits")
def advisor_habits():
    return analyze_spending_habits()


@router.get("/strategy/history")
def advisor_strategy_history(limit: int = 20):
    return {"status": "OK", "items": get_strategy_history(limit)}
