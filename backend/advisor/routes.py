from fastapi import APIRouter
from backend.advisor.service import (
    get_financial_advice,
    analyze_spending_habits,
)

router = APIRouter(prefix="/advisor", tags=["Advisor"])


@router.get("/summary")
def advisor_summary():
    return get_financial_advice()

@router.get("/habits")
def advisor_habits():
    return analyze_spending_habits()