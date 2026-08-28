from fastapi import APIRouter

from backend.goals.models import FinancialGoalRequest, FinancialGoalUpdateRequest
from backend.goals.service import add_financial_goal, delete_financial_goal, get_financial_goals, update_financial_goal


router = APIRouter(prefix="/goals", tags=["Goals"])


@router.get("")
def goals():
    return get_financial_goals()


@router.post("")
def create_goal(request: FinancialGoalRequest):
    return add_financial_goal(**request.model_dump())


@router.put("/{goal_id}")
def edit_goal(goal_id: int, request: FinancialGoalUpdateRequest):
    return update_financial_goal(goal_id, **request.model_dump())


@router.delete("/{goal_id}")
def remove_goal(goal_id: int):
    return delete_financial_goal(goal_id)
